using System.Globalization;
using System.IO;
using UnityEngine;

/// <summary>
/// Silent per-frame logger for the A/B study. Appends to three CSVs (joint positions, trial
/// events, latency) in a StudyData folder — fixed filenames, opened in append mode, so every
/// participant/session adds rows rather than overwriting. Logs the avatar's own bone positions
/// every frame while a trial is running — deliberately never raw MediaPipe/MeTRAbs landmark
/// coordinates, so every condition/system is measuring the same thing (the avatar's resulting
/// pose) and stays comparable for offset/jitter analysis. The condition column is the single
/// system identifier for a row — logged as "HYTRACK" or "MetaQuest" (internal enum names stay
/// RGB/MetaOnly; see LabelFor) — matching "OptiTrack" from OptitrackDataLogger's rows in the
/// same shared CSV.
///
/// Put this on the "StudyManager" GameObject alongside <see cref="TrackingManager"/>.
/// Keys: T starts a trial, E ends it.
/// </summary>
public class DataLogger : MonoBehaviour
{
    public static DataLogger Instance { get; private set; }

    [Header("Session (set per participant)")]
    public string participantId = "P00";

    [Header("References")]
    public TrackingManager trackingManager;
    [Tooltip("Avatar Animator — every logged joint is read from these bones, never from raw MediaPipe/MeTRAbs coordinates.")]
    public Animator avatarAnimator;

    [Header("Keys")]
    [Tooltip("Was R, but InteractiveObject also binds R to reset the ball — moved to avoid the clash.")]
    public KeyCode startTrialKey = KeyCode.T;
    public KeyCode endTrialKey = KeyCode.E;

    [Header("Sampling")]
    [Tooltip("Kept consistent across DataLogger and OptitrackDataLogger so HYTRACK/MetaOnly/OptiTrack are directly comparable for offset/jitter/latency analysis.")]
    public float logsPerSecond = 6f;

    private StreamWriter jointWriter;
    private StreamWriter eventWriter;
    private StreamWriter latencyWriter;

    private bool trialRunning;
    private int trialId;
    private string sessionId;
    private float nextLogTimeMs;

    // Legs are condition-dependent (IK pose in RGB, retargeted Meta pose in MetaOnly — the
    // condition column records which); upper body is always Quest-driven (AvatarHandIK + head
    // tracking) regardless of condition. Either way, every value here comes from the avatar's
    // own bones, never from MediaPipe.
    private static readonly (HumanBodyBones bone, string joint)[] AvatarBones =
    {
        (HumanBodyBones.LeftUpperLeg,  "left_hip"),
        (HumanBodyBones.RightUpperLeg, "right_hip"),
        (HumanBodyBones.LeftLowerLeg,  "left_knee"),
        (HumanBodyBones.RightLowerLeg, "right_knee"),
        (HumanBodyBones.LeftFoot,      "left_ankle"),
        (HumanBodyBones.RightFoot,     "right_ankle"),
        (HumanBodyBones.LeftUpperArm,  "left_shoulder"),
        (HumanBodyBones.RightUpperArm, "right_shoulder"),
        (HumanBodyBones.LeftLowerArm,  "left_elbow"),
        (HumanBodyBones.RightLowerArm, "right_elbow"),
        (HumanBodyBones.LeftHand,      "left_wrist"),
        (HumanBodyBones.RightHand,     "right_wrist"),
        (HumanBodyBones.Head,          "head"),
    };

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(this);
            return;
        }
        Instance = this;
    }

    void Start()
    {
        string dir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "StudyData");
        Directory.CreateDirectory(dir);
        sessionId = System.DateTime.Now.ToString("yyyyMMdd_HHmmss");

        // Fixed filenames, opened in append mode: every participant/session adds rows to the
        // same running CSVs instead of spawning a new file per run. session_id disambiguates
        // runs since trial_id resets to 1 each session.
        jointWriter = OpenCsvAppend(Path.Combine(dir, "joint_positions.csv"),
            "timestamp_ms,session_id,participant_id,condition,trial_id,joint,x,y,z,confidence");
        eventWriter = OpenCsvAppend(Path.Combine(dir, "trial_events.csv"),
            "timestamp_ms,session_id,participant_id,trial_id,event_type,condition");
        latencyWriter = OpenCsvAppend(Path.Combine(dir, "latency_log.csv"),
            "timestamp_ms,session_id,input_time_ms,avatar_update_time_ms,delta_ms,condition");

        Debug.Log($"[Study] Logging to {dir} (session {sessionId})");
    }

    void Update()
    {
        if (Input.GetKeyDown(startTrialKey))
        {
            StartTrial();
        }
        if (Input.GetKeyDown(endTrialKey))
        {
            EndTrial();
        }

        if (trialRunning)
        {
            float t = NowMs();
            if (t >= nextLogTimeMs)
            {
                nextLogTimeMs = t + (1000f / Mathf.Max(0.01f, logsPerSecond));
                LogAvatarJoints(t);
                LogLatency(t);
            }
        }
    }

    public void StartTrial()
    {
        trialId++;
        trialRunning = true;
        nextLogTimeMs = 0f;
        WriteEvent("TRIAL_START");
        Debug.Log($"[Study] Trial {trialId} START");
    }

    public void EndTrial()
    {
        if (!trialRunning)
        {
            return;
        }
        WriteEvent("TRIAL_END");
        trialRunning = false;
        Debug.Log($"[Study] Trial {trialId} END");
    }

    public void LogConditionSwitch(TrackingManager.Condition condition)
    {
        // event_type carries the new condition; the condition column repeats it for filtering.
        if (eventWriter == null)
        {
            return;
        }
        eventWriter.WriteLine(string.Join(",",
            F(NowMs()), sessionId, participantId, Itoa(trialId), "CONDITION_SWITCH", LabelFor(condition)));
    }

    private void LogAvatarJoints(float t)
    {
        if (avatarAnimator == null)
        {
            return;
        }

        foreach (var (bone, joint) in AvatarBones)
        {
            WriteJoint(t, joint, avatarAnimator.GetBoneTransform(bone), 1f);
        }
    }

    private void LogLatency(float t)
    {
        // TODO(hardware): input_time_ms needs the receiver to expose the arrival time of the
        // UDP packet that produced the current pose. Until then avatar_update_time is logged
        // and delta is left blank so the schema is stable.
        if (latencyWriter == null)
        {
            return;
        }
        latencyWriter.WriteLine(string.Join(",",
            F(t), sessionId, "", F(t), "", ConditionLabel()));
    }

    private void WriteJoint(float t, string joint, Transform tf, float confidence)
    {
        if (jointWriter == null || tf == null)
        {
            return;
        }
        Vector3 p = tf.position;
        jointWriter.WriteLine(string.Join(",",
            F(t), sessionId, participantId, ConditionLabel(), Itoa(trialId), joint,
            F(p.x), F(p.y), F(p.z), F(confidence)));
    }

    private void WriteEvent(string eventType)
    {
        if (eventWriter == null)
        {
            return;
        }
        eventWriter.WriteLine(string.Join(",",
            F(NowMs()), sessionId, participantId, Itoa(trialId), eventType, ConditionLabel()));
    }

    private string ConditionLabel()
    {
        return trackingManager != null ? LabelFor(trackingManager.Current) : "Unknown";
    }

    // Single-column system identifier for the CSV. Internal enum names (RGB/MetaOnly) stay as
    // they are — TrackingManager/LegSimulator depend on them — only the logged label changes.
    private static string LabelFor(TrackingManager.Condition condition)
    {
        switch (condition)
        {
            case TrackingManager.Condition.RGB: return "HYTRACK";
            case TrackingManager.Condition.MetaOnly: return "MetaQuest";
            default: return condition.ToString();
        }
    }

    private static float NowMs()
    {
        // Shared clock across all rows in this session — the key advantage of in-scene logging.
        return Time.realtimeSinceStartup * 1000f;
    }

    private static StreamWriter OpenCsvAppend(string path, string header)
    {
        bool isNew = !File.Exists(path);
        var w = new StreamWriter(path, append: true) { AutoFlush = true };
        if (isNew)
        {
            w.WriteLine(header);
        }
        return w;
    }

    private static string F(float v)
    {
        return v.ToString("F4", CultureInfo.InvariantCulture);
    }

    private static string Itoa(int v)
    {
        return v.ToString(CultureInfo.InvariantCulture);
    }

    void OnApplicationQuit()
    {
        CloseAll();
    }

    void OnDestroy()
    {
        if (Instance == this)
        {
            Instance = null;
        }
        CloseAll();
    }

    private void CloseAll()
    {
        jointWriter?.Dispose();
        eventWriter?.Dispose();
        latencyWriter?.Dispose();
        jointWriter = null;
        eventWriter = null;
        latencyWriter = null;
    }
}

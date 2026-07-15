using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

/// <summary>
/// Silent per-frame logger for the A/B study. Writes three CSVs (joint positions, trial
/// events, latency) into a StudyData folder. Logs BOTH the RGB (MediaPipe) and Quest leg
/// joints every frame while a trial is running, regardless of the active condition, so the
/// two systems can be compared post-hoc on a shared clock.
///
/// Put this on the "StudyManager" GameObject alongside <see cref="TrackingManager"/>.
/// Keys: R starts a trial, E ends it.
/// </summary>
public class DataLogger : MonoBehaviour
{
    public static DataLogger Instance { get; private set; }

    [Header("Session (set per participant)")]
    public string participantId = "P00";

    [Header("References")]
    public TrackingManager trackingManager;
    [Tooltip("RGB source — read for the 'rgb' joint rows.")]
    public MediaPipePoseReceiver rgbPoseProvider;
    [Tooltip("Avatar Animator — leg bones read for the 'quest' joint rows (they carry the retargeted Meta pose in MetaOnly).")]
    public Animator avatarAnimator;

    [Header("Keys")]
    public KeyCode startTrialKey = KeyCode.R;
    public KeyCode endTrialKey = KeyCode.E;

    private StreamWriter jointWriter;
    private StreamWriter eventWriter;
    private StreamWriter latencyWriter;

    private bool trialRunning;
    private int trialId;

    // Leg joints logged for the Quest source, mapped to the same names the RGB source uses
    // so the two are directly comparable.
    private static readonly (HumanBodyBones bone, string joint)[] QuestLegBones =
    {
        (HumanBodyBones.LeftUpperLeg,  "left_hip"),
        (HumanBodyBones.RightUpperLeg, "right_hip"),
        (HumanBodyBones.LeftLowerLeg,  "left_knee"),
        (HumanBodyBones.RightLowerLeg, "right_knee"),
        (HumanBodyBones.LeftFoot,      "left_ankle"),
        (HumanBodyBones.RightFoot,     "right_ankle"),
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
        string stamp = System.DateTime.Now.ToString("yyyyMMdd_HHmmss");

        jointWriter = OpenCsv(Path.Combine(dir, $"joint_positions_{participantId}_{stamp}.csv"),
            "timestamp_ms,participant_id,condition,trial_id,source,joint,x,y,z,confidence");
        eventWriter = OpenCsv(Path.Combine(dir, $"trial_events_{participantId}_{stamp}.csv"),
            "timestamp_ms,participant_id,trial_id,event_type,condition");
        latencyWriter = OpenCsv(Path.Combine(dir, $"latency_log_{participantId}_{stamp}.csv"),
            "timestamp_ms,input_time_ms,avatar_update_time_ms,delta_ms,condition");

        Debug.Log($"[Study] Logging to {dir}");
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
            LogRgbJoints(t);
            LogQuestJoints(t);
            LogLatency(t);
        }
    }

    public void StartTrial()
    {
        trialId++;
        trialRunning = true;
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
            F(NowMs()), participantId, Itoa(trialId), "CONDITION_SWITCH", condition.ToString()));
    }

    private void LogRgbJoints(float t)
    {
        if (rgbPoseProvider == null)
        {
            return;
        }

        // Per-joint visibility isn't exposed by the receiver yet, so confidence is coarse:
        // 1 while the receiver reports tracking, else 0. Refine if the receiver later
        // surfaces per-landmark visibility.
        float confidence = rgbPoseProvider.isTracking ? 1f : 0f;

        WriteJoint(t, "rgb", "left_hip", rgbPoseProvider.leftHip, confidence);
        WriteJoint(t, "rgb", "right_hip", rgbPoseProvider.rightHip, confidence);
        WriteJoint(t, "rgb", "left_knee", rgbPoseProvider.leftKnee, confidence);
        WriteJoint(t, "rgb", "right_knee", rgbPoseProvider.rightKnee, confidence);
        WriteJoint(t, "rgb", "left_ankle", rgbPoseProvider.leftAnkle, confidence);
        WriteJoint(t, "rgb", "right_ankle", rgbPoseProvider.rightAnkle, confidence);
    }

    private void LogQuestJoints(float t)
    {
        if (avatarAnimator == null)
        {
            return;
        }

        // These bones carry the retargeted Meta pose while MetaOnly is active; while RGB is
        // active they carry the IK pose. The condition column records which, so analysis
        // knows what each row represents.
        // TODO(hardware): for a truly simultaneous raw-Quest signal in BOTH conditions,
        // read OVRBody's skeleton joints directly instead of the avatar bones.
        foreach (var (bone, joint) in QuestLegBones)
        {
            WriteJoint(t, "quest", joint, avatarAnimator.GetBoneTransform(bone), 1f);
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
            F(t), "", F(t), "", ConditionLabel()));
    }

    private void WriteJoint(float t, string source, string joint, Transform tf, float confidence)
    {
        if (jointWriter == null || tf == null)
        {
            return;
        }
        Vector3 p = tf.position;
        jointWriter.WriteLine(string.Join(",",
            F(t), participantId, ConditionLabel(), Itoa(trialId), source, joint,
            F(p.x), F(p.y), F(p.z), F(confidence)));
    }

    private void WriteEvent(string eventType)
    {
        if (eventWriter == null)
        {
            return;
        }
        eventWriter.WriteLine(string.Join(",",
            F(NowMs()), participantId, Itoa(trialId), eventType, ConditionLabel()));
    }

    private string ConditionLabel()
    {
        return trackingManager != null ? trackingManager.Current.ToString() : "Unknown";
    }

    private static float NowMs()
    {
        // Shared clock for both sources — the key advantage of in-scene logging.
        return Time.realtimeSinceStartup * 1000f;
    }

    private static StreamWriter OpenCsv(string path, string header)
    {
        var w = new StreamWriter(path, false) { AutoFlush = true };
        w.WriteLine(header);
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

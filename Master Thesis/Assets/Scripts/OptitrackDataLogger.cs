using System.Globalization;
using System.IO;
using UnityEngine;

// Appends to the same joint_positions.csv / trial_events.csv DataLogger writes (fixed
// filenames, append mode, session_id column) so OptiTrack trials merge directly with the
// RGB/MetaOnly rows from RGBFullBodyTrackingSystem. Standalone here since TrackingManager's
// RGB/MetaOnly switching doesn't apply to this scene.
public class OptitrackDataLogger : MonoBehaviour
{
    [Header("Session (set per participant)")]
    public string participantId = "P00";

    [Header("References")]
    public Animator avatarAnimator;

    [Header("Keys")]
    public KeyCode startTrialKey = KeyCode.T;
    public KeyCode endTrialKey = KeyCode.E;

    [Header("Sampling")]
    [Tooltip("Kept consistent across DataLogger and OptitrackDataLogger so HYTRACK/MetaOnly/OptiTrack are directly comparable for offset/jitter/latency analysis.")]
    public float logsPerSecond = 6f;

    private StreamWriter jointWriter;
    private StreamWriter eventWriter;

    private bool trialRunning;
    private int trialId;
    private string sessionId;
    private float nextLogTimeMs;

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

    void Start()
    {
        if (avatarAnimator == null)
        {
            avatarAnimator = GetComponent<Animator>();
        }

        string dir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "StudyData");
        Directory.CreateDirectory(dir);
        sessionId = System.DateTime.Now.ToString("yyyyMMdd_HHmmss");

        jointWriter = OpenCsvAppend(Path.Combine(dir, "joint_positions.csv"),
            "timestamp_ms,session_id,participant_id,condition,trial_id,joint,x,y,z,confidence");
        eventWriter = OpenCsvAppend(Path.Combine(dir, "trial_events.csv"),
            "timestamp_ms,session_id,participant_id,trial_id,event_type,condition");

        Debug.Log($"[Study] OptiTrack logging to {dir} (session {sessionId})");
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
                LogJoints(t);
            }
        }
    }

    public void StartTrial()
    {
        trialId++;
        trialRunning = true;
        nextLogTimeMs = 0f;
        WriteEvent("TRIAL_START");
        Debug.Log($"[Study] OptiTrack trial {trialId} START");
    }

    public void EndTrial()
    {
        if (!trialRunning)
        {
            return;
        }
        WriteEvent("TRIAL_END");
        trialRunning = false;
        Debug.Log($"[Study] OptiTrack trial {trialId} END");
    }

    private void LogJoints(float t)
    {
        if (avatarAnimator == null || jointWriter == null)
        {
            return;
        }

        foreach (var (bone, joint) in AvatarBones)
        {
            Transform tf = avatarAnimator.GetBoneTransform(bone);
            if (tf == null)
            {
                continue;
            }
            Vector3 p = tf.position;
            jointWriter.WriteLine(string.Join(",",
                F(t), sessionId, participantId, "OptiTrack", Itoa(trialId), joint,
                F(p.x), F(p.y), F(p.z), F(1f)));
        }
    }

    private void WriteEvent(string eventType)
    {
        if (eventWriter == null)
        {
            return;
        }
        eventWriter.WriteLine(string.Join(",",
            F(NowMs()), sessionId, participantId, Itoa(trialId), eventType, "OptiTrack"));
    }

    private static float NowMs()
    {
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
        CloseAll();
    }

    private void CloseAll()
    {
        jointWriter?.Dispose();
        eventWriter?.Dispose();
        jointWriter = null;
        eventWriter = null;
    }
}

using UnityEngine;

/// <summary>
/// Drives the within-scene A/B study: switches the lower-body tracking source between the
/// RGB (MediaPipe) pipeline and the MetaOnly (Quest generated legs) pipeline. Only the leg
/// source changes; avatar, environment, lighting and the upper-body Quest tracking stay
/// identical, so the participant cannot tell the conditions apart.
///
/// Put this on an empty "StudyManager" GameObject alongside <see cref="DataLogger"/>.
/// Press C to switch condition (between trials).
/// </summary>
public class TrackingManager : MonoBehaviour
{
    public enum Condition
    {
        RGB,
        MetaOnly
    }

    [Header("Study setup (set per participant)")]
    [Tooltip("Which condition this session starts in — set per the counterbalance order.")]
    public Condition startingCondition = Condition.RGB;
    public KeyCode switchKey = KeyCode.C;

    [Header("Sources")]
    [Tooltip("Existing MediaPipe receiver. Left running in both conditions so switching back to RGB is instant; it just doesn't drive the legs in MetaOnly. DataLogger reads the avatar's own bones, not this receiver directly.")]
    public MediaPipePoseReceiver rgbPoseProvider;
    [Tooltip("Owns the AvatarLegsIK / retargeter hand-off.")]
    public LegSimulator legSimulator;

    public Condition Current { get; private set; }

    void Start()
    {
        ApplyCondition(startingCondition);
    }

    void Update()
    {
        if (Input.GetKeyDown(switchKey))
        {
            SwitchCondition();
        }
    }

    /// <summary>Toggle to the other condition.</summary>
    public void SwitchCondition()
    {
        ApplyCondition(Current == Condition.RGB ? Condition.MetaOnly : Condition.RGB);
    }

    /// <summary>Force a specific condition.</summary>
    public void SetCondition(Condition condition)
    {
        ApplyCondition(condition);
    }

    private void ApplyCondition(Condition condition)
    {
        Current = condition;

        if (condition == Condition.RGB)
        {
            // MediaPipe IK drives the legs; Meta retargeter off.
            if (legSimulator != null)
            {
                legSimulator.DisableMetaLegs();
            }
        }
        else
        {
            // Meta retargeter drives the legs; MediaPipe IK silenced.
            if (legSimulator != null)
            {
                legSimulator.EnableMetaLegs();
            }
        }

        // NOTE: rgbPoseProvider is intentionally NOT disabled here, so switching back to RGB
        // is instant — only its influence on the legs (via AvatarLegsIK) is cut in MetaOnly.

        string driver = condition == Condition.RGB
            ? "legs = MediaPipe IK (AvatarLegsIK on, retargeter off)"
            : "legs = Quest generated (retargeter on, AvatarLegsIK off)";
        Debug.Log($"[Study] Condition -> {condition}  |  {driver}");

        if (DataLogger.Instance != null)
        {
            DataLogger.Instance.LogConditionSwitch(condition);
        }
    }
}

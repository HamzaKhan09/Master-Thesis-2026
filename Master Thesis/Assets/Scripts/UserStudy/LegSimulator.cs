using UnityEngine;

/// <summary>
/// Owns the hand-off between the two leg-tracking systems so they never drive the legs at
/// the same time. In the RGB condition <see cref="AvatarLegsIK"/> drives the legs via IK
/// and the Meta retargeter is off. In the MetaOnly condition the retargeter drives the
/// legs and AvatarLegsIK is silenced.
///
/// AvatarLegsIK is silenced by disabling the component: its OnAnimatorIK stops firing.
/// This matters because OnAnimatorIK runs late in the frame and would otherwise overwrite
/// the bones the retargeter just set.
/// </summary>
public class LegSimulator : MonoBehaviour
{
    [Header("Meta (Quest generated legs)")]
    [Tooltip("The retargeter on the avatar that drives the legs in the MetaOnly condition. " +
             "Accepts the base OVRUnityHumanoidSkeletonRetargeter (full-body retarget) or the " +
             "LegsOnlyRetargeter subclass (legs only — recommended for the study).")]
    public OVRUnityHumanoidSkeletonRetargeter legsRetargeter;

    [Header("RGB (MediaPipe)")]
    [Tooltip("The existing IK driver. Drives the legs in the RGB condition; silenced in MetaOnly.")]
    public AvatarLegsIK avatarLegsIK;

    void Awake()
    {
        // Known start state: Meta legs off. TrackingManager applies the real starting
        // condition in Start().
        if (legsRetargeter != null)
        {
            legsRetargeter.enabled = false;
        }
    }

    /// <summary>MetaOnly: retargeter drives the legs, MediaPipe IK is silenced.</summary>
    public void EnableMetaLegs()
    {
        if (avatarLegsIK != null)
        {
            avatarLegsIK.enabled = false;
        }
        if (legsRetargeter != null)
        {
            legsRetargeter.enabled = true;
        }
    }

    /// <summary>RGB: MediaPipe IK drives the legs, retargeter is silenced.</summary>
    public void DisableMetaLegs()
    {
        if (legsRetargeter != null)
        {
            legsRetargeter.enabled = false;
        }
        if (avatarLegsIK != null)
        {
            avatarLegsIK.enabled = true;
        }
    }
}

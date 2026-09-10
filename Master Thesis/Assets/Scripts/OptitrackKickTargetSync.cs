using UnityEngine;

// LimbCollider triggers that kick the ball live on these targets (originally owned by
// AvatarLegsIK.leftLegIKTarget/rightLegIKTarget). OptitrackSkeletonAnimator drives the real
// foot bones directly, not through AvatarLegsIK, so nothing else moves these targets — glue
// them to the retargeted feet each frame. Mirrors LegsOnlyRetargeter.SyncKickTargetsToRetargetedFeet().
public class OptitrackKickTargetSync : MonoBehaviour
{
    public Animator animator;
    public Transform leftFootKickTarget;
    public Transform rightFootKickTarget;

    private Transform leftFoot;
    private Transform rightFoot;

    void Start()
    {
        if (animator == null)
        {
            animator = GetComponent<Animator>();
        }

        if (animator == null)
        {
            return;
        }

        leftFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
        rightFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);
    }

    void LateUpdate()
    {
        if (leftFoot != null && leftFootKickTarget != null)
        {
            leftFootKickTarget.SetPositionAndRotation(leftFoot.position, leftFoot.rotation);
        }

        if (rightFoot != null && rightFootKickTarget != null)
        {
            rightFootKickTarget.SetPositionAndRotation(rightFoot.position, rightFoot.rotation);
        }
    }
}

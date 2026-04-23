using UnityEngine;

public class AvatarHandIK : MonoBehaviour
{
    public Animator animator; // Avatar's Animator
    public Transform vrLeftHandTarget; // VR Left Hand Target
    public Transform vrRightHandTarget; // VR Right Hand Target

    public float ikWeight = 1.0f; // How strongly IK follows the target
    public Transform vrHeadTarget;

void OnAnimatorIK(int layerIndex)
{
    if (animator == null) return;

    // Left Hand
    if (vrLeftHandTarget != null)
    {
        animator.SetIKPositionWeight(AvatarIKGoal.LeftHand, ikWeight);
        animator.SetIKRotationWeight(AvatarIKGoal.LeftHand, ikWeight);

        animator.SetIKPosition(AvatarIKGoal.LeftHand, vrLeftHandTarget.position);
        animator.SetIKRotation(AvatarIKGoal.LeftHand, vrLeftHandTarget.rotation);
    }

    // Right Hand
    if (vrRightHandTarget != null)
    {
        animator.SetIKPositionWeight(AvatarIKGoal.RightHand, ikWeight);
        animator.SetIKRotationWeight(AvatarIKGoal.RightHand, ikWeight);

        animator.SetIKPosition(AvatarIKGoal.RightHand, vrRightHandTarget.position);
        animator.SetIKRotation(AvatarIKGoal.RightHand, vrRightHandTarget.rotation);
    }

    // Head LookAt
    if (vrHeadTarget != null)
    {
        animator.SetLookAtWeight(ikWeight);
        animator.SetLookAtPosition(vrHeadTarget.position);
    }
}
}
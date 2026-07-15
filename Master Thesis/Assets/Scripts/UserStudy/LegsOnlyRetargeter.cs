using UnityEngine;

/// <summary>
/// Restricts Meta's built-in humanoid retargeter to the leg and foot bone sections
/// only. Attach this instead of <see cref="OVRUnityHumanoidSkeletonRetargeter"/> on the
/// avatar so the Quest full-body skeleton drives ONLY the legs; the upper body stays on
/// the existing Quest hand/head + hand-IK setup. This keeps the MetaOnly study condition
/// differing from RGB by legs alone.
///
/// Requires (same GameObject as the avatar Animator): this component with Skeleton Type =
/// FullBody, plus an <see cref="OVRBody"/> data provider so the FullBody skeleton is fed in.
/// </summary>
public class LegsOnlyRetargeter : OVRUnityHumanoidSkeletonRetargeter
{
    [Header("Diagnostic")]
    [Tooltip("TEMPORARY: when on, retargets the WHOLE body (no legs-only masking). Use to check " +
             "whether Meta body-tracking data is arriving at all: if the upper body follows you " +
             "with this on, data is fine and the issue is the masking; if nothing moves, there is " +
             "no body-tracking data (headset/OVRManager settings). Turn OFF for the real study.")]
    public bool debugDriveFullBody = false;

    [Tooltip("TEMPORARY: logs whether the body-tracking skeleton is valid and how many bones it " +
             "carries, once per second. If valid=False you have no body data; if valid=True but " +
             "legs stay straight, the leg joints aren't being generated (raise Body Tracking " +
             "Fidelity to High). Turn OFF for the real study.")]
    public bool logBodyData = false;
    private float _nextBodyLogTime;
    private AvatarLegsIK _legIk;
    private Transform _leftFoot;
    private Transform _rightFoot;

    protected override void Start()
    {
        if (!debugDriveFullBody)
        {
            // The section arrays are [SerializeField] protected on the base class, so we can
            // shrink them here before base.Start() builds its retargeting tables from them.
            OVRHumanBodyBonesMappings.BodySection[] legsOnly =
            {
                OVRHumanBodyBonesMappings.BodySection.LeftLeg,
                OVRHumanBodyBonesMappings.BodySection.LeftFoot,
                OVRHumanBodyBonesMappings.BodySection.RightLeg,
                OVRHumanBodyBonesMappings.BodySection.RightFoot
            };

            // Rotation only. Aligning = copy the source joint ANGLES onto the avatar's leg
            // bones (keeps the avatar's own bone lengths). We deliberately do NOT position-
            // retarget the legs: positioning moves the leg bones to the tracked person's
            // absolute joint positions, which stretches/shrinks the avatar into a distorted
            // shape.
            OVRHumanBodyBonesMappings.BodySection[] none =
                new OVRHumanBodyBonesMappings.BodySection[0];

            _fullBodySectionsToAlign = legsOnly;
            _bodySectionsToAlign = legsOnly;
            _fullBodySectionToPosition = none;
            _bodySectionToPosition = none;
        }

        base.Start();
        Animator animator = GetComponent<Animator>();
        _legIk = GetComponent<AvatarLegsIK>();
        if (animator != null)
        {
            _leftFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
            _rightFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);
        }
    }

    // In RGB mode AvatarLegsIK moves its foot IK targets, which already own the
    // LimbCollider triggers that kick the ball. MetaOnly disables AvatarLegsIK,
    // so those targets otherwise freeze even though the retargeted foot bones move.
    // Keep the existing, proven colliders aligned with Meta's final foot pose.
    private void SyncKickTargetsToRetargetedFeet()
    {
        if (_legIk == null)
        {
            return;
        }

        if (_leftFoot != null && _legIk.leftLegIKTarget != null)
        {
            _legIk.leftLegIKTarget.SetPositionAndRotation(_leftFoot.position, _leftFoot.rotation);
        }

        if (_rightFoot != null && _legIk.rightLegIKTarget != null)
        {
            _legIk.rightLegIKTarget.SetPositionAndRotation(_rightFoot.position, _rightFoot.rotation);
        }
    }

    // The base retargeter applies the pose in Update(). But the avatar's Animator (Stand--Idle)
    // evaluates AFTER Update and overwrites the retargeted legs back to straight every frame, so
    // the legs never move even though live leg data is arriving. Suppress the Update-time apply
    // and re-run the whole retarget in LateUpdate — after the animation and after OnAnimatorIK —
    // so the retargeted legs land last and stick. (Hand/head OnAnimatorIK drives different bones,
    // so there's no conflict.)
    protected override void Update()
    {
        // Intentionally empty: retargeting is deferred to LateUpdate.
    }

    void LateUpdate()
    {
        base.Update();
        SyncKickTargetsToRetargetedFeet();

        if (!logBodyData || Time.time < _nextBodyLogTime)
        {
            return;
        }
        _nextBodyLogTime = Time.time + 1f;

        int boneCount = Bones != null ? Bones.Count : 0;

        // Read the SOURCE (Meta) leg bones directly. If these rotations do not change as you
        // walk, the leg joints aren't being generated — it's a Fidelity/Link problem, not the
        // retargeter. If they DO change but the avatar legs stay straight, it's retargeting.
        string legInfo = "no leg bones found";
        if (Bones != null)
        {
            foreach (var b in Bones)
            {
                if (b.Id == BoneId.FullBody_LeftUpperLeg && b.Transform != null)
                {
                    Vector3 e = b.Transform.localRotation.eulerAngles;
                    legInfo = $"L_UpperLeg local euler=({e.x:F0},{e.y:F0},{e.z:F0})";
                    break;
                }
            }
        }

        Debug.Log($"[Retarget] IsDataValid={IsDataValid}  IsHighConfidence={IsDataHighConfidence}  " +
                  $"sourceBones={boneCount}  skeletonType={GetSkeletonType()}  {legInfo}");
    }
}

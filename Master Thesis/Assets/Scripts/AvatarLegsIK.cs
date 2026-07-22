using UnityEngine;
using Kinect = Windows.Kinect;

public class AvatarLegsIK : MonoBehaviour
{
    public enum LegTrackingSource
    {
        Kinect,
        MediaPipe
    }

    [Header("Tracking Source")]
    public LegTrackingSource trackingSource = LegTrackingSource.Kinect;

    [Header("Kinect")]
    public BodySourceManager BodySourceManager;
    private Kinect.Body trackedBody;

    [Header("MediaPipe")]
    public MediaPipePoseReceiver mediaPipePoseReceiver;
    public bool moveRootWithMediaPipeHips = false;
    public Vector3 mediaPipeRootOffset = Vector3.zero;
    public Vector3 mediaPipeIKOffset = Vector3.zero;
    public float mediaPipeIKScale = 1f;
    [Tooltip("Cache the avatar hip center once at Start instead of reading live leg bones every frame. Stops the IK solver's own body shift from feeding back into both foot targets (moving one leg dragging the other along). Turn off to compare against the live-bone behaviour.")]
    public bool useStableHipCenter = true;
    [Tooltip("How fast the foot/knee IK targets chase the incoming pose. Higher = snappier, less lag (but more jitter). This is the dominant latency knob for MediaPipe/MeTRAbs tracking. Try 10-20.")]
    public float mediaPipeTargetFollowSpeed = 14f;

    [Header("Diagnostics")]
    [Tooltip("Writes per-frame IK target data to Logs/leg_ik_debug.csv in the project folder for offline analysis.")]
    public bool logTargetsToFile = true;
    public bool logMediaPipeLegLengths = true;
    public float legLengthLogInterval = 1f;
    public bool logMediaPipeIKTargets = true;
    [Tooltip("Logs the actual solved foot/knee/pelvis BONE positions vs the commanded IK targets. Use it to find whether a correct target is being rendered as a wrong pose (something overriding the IK after OnAnimatorIK).")]
    public bool logBonePositions = false;
    public float boneLogInterval = 0.5f;
    private float nextBoneLogTime;

    [Header("Foot Grounding")]
    public bool groundFeetToFloor = true;
    public float mediaPipeGroundY = 0f;
    public float groundFollowSpeed = 10f;

    [Header("Jump (HMD vertical)")]
    [Tooltip("Same head transform VRRootFollower reads (its vrHeadTarget, e.g. OVRCameraRig's CenterEyeAnchor). Only used to detect the headset rising above its calibrated standing height (a jump) — downward movement is ignored on purpose, so this doesn't interact with the separate, still-open crouch issue.")]
    public Transform vrHeadTransform;
    [Tooltip("Press while standing normally to reset the jump baseline (e.g. after recentering, or at the start of a session).")]
    public KeyCode recalibrateHeadHeightKey = KeyCode.J;
    [Tooltip("Head-height rise (metres) below which it's treated as standing sway/tracking noise, not a jump. Natural head bob while standing is a few mm to ~1cm; real jumps clear this easily.")]
    public float jumpDeadZone = 0.03f;
    [Tooltip("How fast the applied jump lift chases a real jump. Kept separate from groundFollowSpeed (tuned slow, for gentle depth-drift correction) so an actual jump doesn't visibly lag behind your real motion.")]
    public float jumpFollowSpeed = 25f;
    private float calibratedHeadY;
    private bool headHeightCalibrated;

    [Header("IK Targets")]
    public Transform leftLegIKTarget, rightLegIKTarget;
    public Transform leftKneeIKHint, rightKneeIKHint;
    public Transform avatarRoot;

    [Header("IK Weights")]
    public float footPositionWeight = 1.0f;
    public float footRotationWeight = 0.0f;
    public float kneeHintWeight = 1.0f;
    public float kneeHintForwardBias = 0.6f;

    private Animator animator;
    private Vector3 cachedHipOffset;
    private bool hipOffsetCalibrated;
    private float nextLegLengthLogTime;
    private System.IO.StreamWriter csvWriter;
    private System.IO.StreamWriter legLengthWriter;
    private System.IO.StreamWriter boneWriter;

    void Awake()
    {
        animator = GetComponent<Animator>();
    }

    void Start()
    {
        // Capture the hip-center offset once, in the authored rest pose, while the
        // humanoid bones are still valid. Reading the live bone midpoint every frame
        // lets the IK solver's own body shift feed back into both foot targets, so
        // moving one leg drags the planted one along.
        if (useStableHipCenter && animator != null)
        {
            Transform leftHipBone = animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
            Transform rightHipBone = animator.GetBoneTransform(HumanBodyBones.RightUpperLeg);
            if (leftHipBone != null && rightHipBone != null)
            {
                cachedHipOffset = (leftHipBone.position + rightHipBone.position) * 0.5f - transform.position;
                hipOffsetCalibrated = true;
            }
        }

        if (vrHeadTransform != null)
        {
            calibratedHeadY = vrHeadTransform.position.y;
            headHeightCalibrated = true;
        }
    }

    void OnDestroy()
    {
        if (csvWriter != null)
        {
            csvWriter.Dispose();
            csvWriter = null;
        }

        if (legLengthWriter != null)
        {
            legLengthWriter.Dispose();
            legLengthWriter = null;
        }

        if (boneWriter != null)
        {
            boneWriter.Dispose();
            boneWriter = null;
        }
    }

    void Update()
    {
        HandleSourceSwitchInput();

        if (trackingSource == LegTrackingSource.MediaPipe)
        {
            UpdateIKTargetsFromMediaPipe();
            return;
        }

        if (BodySourceManager == null)
        {
            return;
        }

        Kinect.Body[] data = BodySourceManager.GetData();
        if (data == null)
        {
            return;
        }

        trackedBody = null;
        foreach (Kinect.Body body in data)
        {
            if (body != null && body.IsTracked)
            {
                trackedBody = body;
                break;
            }
        }

        if (trackedBody != null)
        {
            UpdateIKTargets();
        }
    }

    void LateUpdate()
    {
        // Runs after the Animator's IK solve, so bone positions here are the final
        // rendered pose. Compares the solved foot/knee/pelvis bones against the
        // commanded IK targets: a large foot delta means something is overriding the
        // humanoid IK (e.g. an Animation Rigging constraint or a second component).
        if (!logBonePositions || animator == null || Time.time < nextBoneLogTime)
        {
            return;
        }
        nextBoneLogTime = Time.time + boneLogInterval;

        Transform pelvis = animator.GetBoneTransform(HumanBodyBones.Hips);
        Transform lFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
        Transform rFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);
        Transform lKnee = animator.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
        Transform rKnee = animator.GetBoneTransform(HumanBodyBones.RightLowerLeg);

        Vector3 lFootBone = lFoot != null ? lFoot.position : Vector3.zero;
        Vector3 rFootBone = rFoot != null ? rFoot.position : Vector3.zero;
        Vector3 lTarget = leftLegIKTarget != null ? leftLegIKTarget.position : Vector3.zero;
        Vector3 rTarget = rightLegIKTarget != null ? rightLegIKTarget.position : Vector3.zero;

        if (boneWriter == null)
        {
            string dir = System.IO.Path.Combine(Application.dataPath, "..", "Logs");
            System.IO.Directory.CreateDirectory(dir);
            boneWriter = new System.IO.StreamWriter(System.IO.Path.Combine(dir, "bone_vs_target.csv"), false)
            {
                AutoFlush = true
            };
            boneWriter.WriteLine(
                "time,pelvisY," +
                "LfootBoneX,LfootBoneY,LfootBoneZ,LtargetX,LtargetY,LtargetZ,Ldist," +
                "RfootBoneX,RfootBoneY,RfootBoneZ,RtargetX,RtargetY,RtargetZ,Rdist," +
                "LkneeY,RkneeY");
        }

        boneWriter.WriteLine(
            $"{Time.time:F2},{(pelvis != null ? pelvis.position.y : 0f):F3}," +
            $"{lFootBone.x:F3},{lFootBone.y:F3},{lFootBone.z:F3},{lTarget.x:F3},{lTarget.y:F3},{lTarget.z:F3},{Vector3.Distance(lFootBone, lTarget):F3}," +
            $"{rFootBone.x:F3},{rFootBone.y:F3},{rFootBone.z:F3},{rTarget.x:F3},{rTarget.y:F3},{rTarget.z:F3},{Vector3.Distance(rFootBone, rTarget):F3}," +
            $"{(lKnee != null ? lKnee.position.y : 0f):F3},{(rKnee != null ? rKnee.position.y : 0f):F3}");
    }

    private void HandleSourceSwitchInput()
    {
        if (Input.GetKeyDown(KeyCode.M))
        {
            trackingSource = LegTrackingSource.MediaPipe;
            Debug.Log("Switched to MediaPipe lower body tracking.");
        }
        else if (Input.GetKeyDown(KeyCode.K))
        {
            trackingSource = LegTrackingSource.Kinect;
            Debug.Log("Switched to Kinect lower body tracking.");
        }

        if (vrHeadTransform != null && Input.GetKeyDown(recalibrateHeadHeightKey))
        {
            calibratedHeadY = vrHeadTransform.position.y;
            headHeightCalibrated = true;
            Debug.Log("Recalibrated standing head height for jump detection.");
        }
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (animator == null) return;

        if (leftLegIKTarget != null)
        {
            animator.SetIKPositionWeight(AvatarIKGoal.LeftFoot, footPositionWeight);
            animator.SetIKRotationWeight(AvatarIKGoal.LeftFoot, footRotationWeight);
            animator.SetIKPosition(AvatarIKGoal.LeftFoot, leftLegIKTarget.position);
            animator.SetIKRotation(AvatarIKGoal.LeftFoot, leftLegIKTarget.rotation);
        }

        if (rightLegIKTarget != null)
        {
            animator.SetIKPositionWeight(AvatarIKGoal.RightFoot, footPositionWeight);
            animator.SetIKRotationWeight(AvatarIKGoal.RightFoot, footRotationWeight);
            animator.SetIKPosition(AvatarIKGoal.RightFoot, rightLegIKTarget.position);
            animator.SetIKRotation(AvatarIKGoal.RightFoot, rightLegIKTarget.rotation);
        }

        if (leftKneeIKHint != null)
        {
            animator.SetIKHintPositionWeight(AvatarIKHint.LeftKnee, kneeHintWeight);
            animator.SetIKHintPosition(AvatarIKHint.LeftKnee, leftKneeIKHint.position);
        }

        if (rightKneeIKHint != null)
        {
            animator.SetIKHintPositionWeight(AvatarIKHint.RightKnee, kneeHintWeight);
            animator.SetIKHintPosition(AvatarIKHint.RightKnee, rightKneeIKHint.position);
        }
    }

    private Vector3 GetAvatarHipCenter()
    {
        Transform leftHipBone = animator != null ? animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg) : null;
        Transform rightHipBone = animator != null ? animator.GetBoneTransform(HumanBodyBones.RightUpperLeg) : null;

        if (leftHipBone != null && rightHipBone != null)
        {
            return (leftHipBone.position + rightHipBone.position) * 0.5f;
        }

        return avatarRoot != null ? avatarRoot.position : transform.position;
    }

    private void UpdateIKTargets()
    {
        Vector3 kinectHipPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.SpineBase]);
        float hipYOffset = 0.91f;
        Vector3 globalOffset = new Vector3(0f, 0f, 2.25f);

        transform.position = new Vector3(
            kinectHipPos.x,
            kinectHipPos.y + hipYOffset,
            kinectHipPos.z) + globalOffset;

        Vector3 leftFootPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleLeft]);
        Vector3 rightFootPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleRight]);
        Vector3 leftKneePos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.KneeLeft]);
        Vector3 rightKneePos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.KneeRight]);

        Vector3 kneeOffset = new Vector3(0f, 0f, 1.8f);
        Vector3 feetOffset = new Vector3(0f, 0.7f, 2.2f);
        leftFootPos += feetOffset;
        rightFootPos += feetOffset;
        leftKneePos += kneeOffset;
        rightKneePos += kneeOffset;

        float targetBlend = Time.deltaTime * 5f;
        if (leftLegIKTarget != null) leftLegIKTarget.position = Vector3.Lerp(leftLegIKTarget.position, leftFootPos, targetBlend);
        if (rightLegIKTarget != null) rightLegIKTarget.position = Vector3.Lerp(rightLegIKTarget.position, rightFootPos, targetBlend);

        Vector3 leftKneeDir = (leftFootPos - leftKneePos).normalized;
        Vector3 rightKneeDir = (rightFootPos - rightKneePos).normalized;
        Vector3 forwardBias = avatarRoot != null ? avatarRoot.forward * 0.7f : transform.forward * 0.7f;
        Vector3 upwardBias = Vector3.up;

        Vector3 leftHintPos = leftKneePos + leftKneeDir * 0.3f + forwardBias + upwardBias;
        Vector3 rightHintPos = rightKneePos + rightKneeDir * 0.3f + forwardBias + upwardBias;

        if (leftKneeIKHint != null) leftKneeIKHint.position = Vector3.Lerp(leftKneeIKHint.position, leftHintPos, targetBlend);
        if (rightKneeIKHint != null) rightKneeIKHint.position = Vector3.Lerp(rightKneeIKHint.position, rightHintPos, targetBlend);
    }

    private void UpdateIKTargetsFromMediaPipe()
    {
        if (mediaPipePoseReceiver == null)
        {
            return;
        }

        Transform leftHip = mediaPipePoseReceiver.leftHip;
        Transform rightHip = mediaPipePoseReceiver.rightHip;
        Transform leftKnee = mediaPipePoseReceiver.leftKnee;
        Transform rightKnee = mediaPipePoseReceiver.rightKnee;
        Transform leftAnkle = mediaPipePoseReceiver.leftAnkle;
        Transform rightAnkle = mediaPipePoseReceiver.rightAnkle;

        if (leftKnee == null || rightKnee == null || leftAnkle == null || rightAnkle == null)
        {
            return;
        }

        LogMediaPipeLegLengths(leftHip, rightHip, leftKnee, rightKnee, leftAnkle, rightAnkle);

        float targetBlend = Time.deltaTime * mediaPipeTargetFollowSpeed;
        Vector3 mpHipCenter = GetMediaPipeScaleCenter(leftHip, rightHip, leftAnkle, rightAnkle);

        bool trackingValid = mediaPipePoseReceiver.isTracking;

        Vector3 avatarHipCenter = (useStableHipCenter && hipOffsetCalibrated)
            ? transform.position + cachedHipOffset
            : GetAvatarHipCenter();
        Vector3 scaledLeftKnee = avatarHipCenter + (leftKnee.position - mpHipCenter) * mediaPipeIKScale + mediaPipeIKOffset;
        Vector3 scaledRightKnee = avatarHipCenter + (rightKnee.position - mpHipCenter) * mediaPipeIKScale + mediaPipeIKOffset;
        Vector3 scaledLeftAnkle = avatarHipCenter + (leftAnkle.position - mpHipCenter) * mediaPipeIKScale + mediaPipeIKOffset;
        Vector3 scaledRightAnkle = avatarHipCenter + (rightAnkle.position - mpHipCenter) * mediaPipeIKScale + mediaPipeIKOffset;

        // Vertical grounding: shift the avatar root so the lower foot rests on the floor.
        // Gated on isTracking so startup (when all spheres overlap) doesn't sink the avatar.
        if (groundFeetToFloor && trackingValid)
        {
            // Jump lift: MediaPipe's landmarks are hip-relative, so a real jump (whole body
            // translating upward with the leg pose roughly unchanged) is invisible to the
            // foot-scaling math above — it would just re-plant the lower foot back to the
            // floor every frame. The HMD's own absolute vertical tracking is the one signal
            // that actually sees a jump, so fold it in here as an upward-only offset to the
            // floor target. Downward deviation is ignored on purpose (crouch is a separate,
            // already-open issue with its own history — see project memory).
            float jumpLift = 0f;
            if (vrHeadTransform != null && headHeightCalibrated)
            {
                float aboveBaseline = vrHeadTransform.position.y - calibratedHeadY;
                jumpLift = aboveBaseline > jumpDeadZone ? aboveBaseline - jumpDeadZone : 0f;
            }

            float lowestFootY = Mathf.Min(scaledLeftAnkle.y, scaledRightAnkle.y);
            float desiredRootY = transform.position.y + (mediaPipeGroundY + jumpLift - lowestFootY);
            // Use the faster jump speed only while actually airborne; revert to the normal
            // gentle grounding speed once back near baseline, so standing behaviour is
            // unchanged from before this fix.
            float effectiveFollowSpeed = jumpLift > 0f ? Mathf.Max(groundFollowSpeed, jumpFollowSpeed) : groundFollowSpeed;
            Vector3 groundedRoot = transform.position;
            groundedRoot.y = Mathf.Lerp(groundedRoot.y, desiredRootY, Time.deltaTime * effectiveFollowSpeed);
            transform.position = groundedRoot;
        }

        if (moveRootWithMediaPipeHips && leftHip != null && rightHip != null)
        {
            Vector3 hipCenter = avatarHipCenter + ((leftHip.position + rightHip.position) * 0.5f - mpHipCenter) * mediaPipeIKScale;
            Vector3 rootTarget = hipCenter + mediaPipeRootOffset;
            if (avatarRoot != null)
            {
                Vector3 rootDelta = rootTarget - avatarRoot.position;
                transform.position = Vector3.Lerp(transform.position, transform.position + rootDelta, targetBlend);
            }
            else
            {
                transform.position = Vector3.Lerp(transform.position, rootTarget, targetBlend);
            }

            if (logMediaPipeLegLengths && Time.time >= nextLegLengthLogTime - legLengthLogInterval + 0.05f)
            {
                Debug.Log($"MediaPipe root follow | target hips {rootTarget}, avatar hips {(avatarRoot != null ? avatarRoot.position : transform.position)}");
            }
        }

        if (leftLegIKTarget != null)
        {
            leftLegIKTarget.position = Vector3.Lerp(leftLegIKTarget.position, scaledLeftAnkle, targetBlend);
        }

        if (rightLegIKTarget != null)
        {
            rightLegIKTarget.position = Vector3.Lerp(rightLegIKTarget.position, scaledRightAnkle, targetBlend);
        }






Vector3 leftLegDir =
    (scaledLeftAnkle - scaledLeftKnee).normalized;

Vector3 rightLegDir =
    (scaledRightAnkle - scaledRightKnee).normalized;

Vector3 kneeForward =
    transform.forward * kneeHintForwardBias;

Vector3 leftHintPos =
    scaledLeftKnee -
    leftLegDir * 0.25f +
    kneeForward;

Vector3 rightHintPos =
    scaledRightKnee -
    rightLegDir * 0.25f +
    kneeForward;

if (leftKneeIKHint != null)
{
    leftKneeIKHint.position =
        Vector3.Lerp(
            leftKneeIKHint.position,
            leftHintPos,
            targetBlend);
}

if (rightKneeIKHint != null)
{
    rightKneeIKHint.position =
        Vector3.Lerp(
            rightKneeIKHint.position,
            rightHintPos,
            targetBlend);
}






        if (logTargetsToFile)
        {
            WriteCsvFrame(trackingValid, avatarHipCenter, mpHipCenter,
                leftKnee.position, rightKnee.position,
                leftAnkle.position, rightAnkle.position,
                scaledLeftKnee, scaledRightKnee,
                scaledLeftAnkle, scaledRightAnkle,
                leftHintPos, rightHintPos);
        }

        LogMediaPipeIKTargets(scaledLeftKnee, scaledRightKnee, scaledLeftAnkle, scaledRightAnkle);
    }

    private void WriteCsvFrame(
        bool trackingValid,
        Vector3 avatarHipCenter,
        Vector3 mpHipCenter,
        Vector3 rawLeftKnee,
        Vector3 rawRightKnee,
        Vector3 rawLeftAnkle,
        Vector3 rawRightAnkle,
        Vector3 targetLeftKnee,
        Vector3 targetRightKnee,
        Vector3 targetLeftAnkle,
        Vector3 targetRightAnkle,
        Vector3 leftKneeHintPos,
        Vector3 rightKneeHintPos)
    {
        if (csvWriter == null)
        {
            string logDirectory = System.IO.Path.Combine(Application.dataPath, "..", "Logs");
            System.IO.Directory.CreateDirectory(logDirectory);
            csvWriter = new System.IO.StreamWriter(System.IO.Path.Combine(logDirectory, "leg_ik_debug.csv"), false)
            {
                AutoFlush = true
            };
            csvWriter.WriteLine(
                "time,tracking,rootX,rootY,rootZ,hipCenterX,hipCenterY,hipCenterZ," +
                "mpHipX,mpHipY,mpHipZ," +
                "rawLKneeX,rawLKneeY,rawLKneeZ,rawRKneeX,rawRKneeY,rawRKneeZ," +
                "rawLAnkleX,rawLAnkleY,rawLAnkleZ,rawRAnkleX,rawRAnkleY,rawRAnkleZ," +
                "targetLKneeX,targetLKneeY,targetLKneeZ,targetRKneeX,targetRKneeY,targetRKneeZ," +
                "targetLAnkleX,targetLAnkleY,targetLAnkleZ,targetRAnkleX,targetRAnkleY,targetRAnkleZ," +
                "hintLX,hintLY,hintLZ,hintRX,hintRY,hintRZ");
        }

        csvWriter.WriteLine(string.Join(",",
            Time.time.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
            trackingValid ? "1" : "0",
            Csv(transform.position),
            Csv(avatarHipCenter),
            Csv(mpHipCenter),
            Csv(rawLeftKnee),
            Csv(rawRightKnee),
            Csv(rawLeftAnkle),
            Csv(rawRightAnkle),
            Csv(targetLeftKnee),
            Csv(targetRightKnee),
            Csv(targetLeftAnkle),
            Csv(targetRightAnkle),
            Csv(leftKneeHintPos),
            Csv(rightKneeHintPos)));
    }

    private static string Csv(Vector3 value)
    {
        return string.Format(System.Globalization.CultureInfo.InvariantCulture,
            "{0:F3},{1:F3},{2:F3}", value.x, value.y, value.z);
    }

    private Vector3 ConvertKinectToUnity(Kinect.Joint joint)
    {
        return new Vector3(joint.Position.X, joint.Position.Y, -joint.Position.Z);
    }

    private Vector3 GetMediaPipeScaleCenter(Transform leftHip, Transform rightHip, Transform leftAnkle, Transform rightAnkle)
    {
        if (leftHip != null && rightHip != null)
        {
            return (leftHip.position + rightHip.position) * 0.5f;
        }

        return (leftAnkle.position + rightAnkle.position) * 0.5f;
    }

    private void LogMediaPipeLegLengths(
        Transform leftHip,
        Transform rightHip,
        Transform leftKnee,
        Transform rightKnee,
        Transform leftAnkle,
        Transform rightAnkle)
    {
        if (!logMediaPipeLegLengths || Time.time < nextLegLengthLogTime)
        {
            return;
        }

        nextLegLengthLogTime = Time.time + legLengthLogInterval;

        float leftMpThigh = leftHip != null ? Vector3.Distance(leftHip.position, leftKnee.position) : 0f;
        float leftMpShin = Vector3.Distance(leftKnee.position, leftAnkle.position);
        float rightMpThigh = rightHip != null ? Vector3.Distance(rightHip.position, rightKnee.position) : 0f;
        float rightMpShin = Vector3.Distance(rightKnee.position, rightAnkle.position);

        float leftAvatarThigh = GetAvatarBoneLength(HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg);
        float leftAvatarShin = GetAvatarBoneLength(HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot);
        float rightAvatarThigh = GetAvatarBoneLength(HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg);
        float rightAvatarShin = GetAvatarBoneLength(HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot);

        float mpLegTotal = (leftMpThigh + leftMpShin + rightMpThigh + rightMpShin) * 0.5f;
        float avatarLegTotal = (leftAvatarThigh + leftAvatarShin + rightAvatarThigh + rightAvatarShin) * 0.5f;
        float suggestedScale = mpLegTotal > 0.01f ? avatarLegTotal / mpLegTotal : mediaPipeIKScale;

        string legLengthSummary =
            $"MediaPipe leg lengths | " +
            $"L thigh {leftMpThigh:F2}/{leftAvatarThigh:F2}, L shin {leftMpShin:F2}/{leftAvatarShin:F2}, " +
            $"R thigh {rightMpThigh:F2}/{rightAvatarThigh:F2}, R shin {rightMpShin:F2}/{rightAvatarShin:F2} | " +
            $"Suggested mediaPipeIKScale: {suggestedScale:F2} (current: {mediaPipeIKScale:F2})";

        Debug.Log(legLengthSummary);

        if (legLengthWriter == null)
        {
            string logDirectory = System.IO.Path.Combine(Application.dataPath, "..", "Logs");
            System.IO.Directory.CreateDirectory(logDirectory);
            legLengthWriter = new System.IO.StreamWriter(System.IO.Path.Combine(logDirectory, "leg_lengths.txt"), false)
            {
                AutoFlush = true
            };
        }

        legLengthWriter.WriteLine($"{Time.time:F1} {legLengthSummary}");
    }

    private void LogMediaPipeIKTargets(Vector3 leftKnee, Vector3 rightKnee, Vector3 leftAnkle, Vector3 rightAnkle)
    {
        if (!logMediaPipeIKTargets || Time.time < nextLegLengthLogTime - legLengthLogInterval + 0.1f)
        {
            return;
        }

        Vector3 hips = avatarRoot != null ? avatarRoot.position : transform.position;
        Debug.Log(
            $"MediaPipe IK targets | hips {hips}, " +
            $"LK {leftKnee}, LA {leftAnkle}, RK {rightKnee}, RA {rightAnkle}");
    }

    private float GetAvatarBoneLength(HumanBodyBones startBone, HumanBodyBones endBone)
    {
        if (animator == null)
        {
            return 0f;
        }

        Transform start = animator.GetBoneTransform(startBone);
        Transform end = animator.GetBoneTransform(endBone);

        if (start == null || end == null)
        {
            return 0f;
        }

        return Vector3.Distance(start.position, end.position);
    }
}

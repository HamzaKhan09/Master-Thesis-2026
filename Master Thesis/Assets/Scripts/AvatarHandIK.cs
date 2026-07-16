using UnityEngine;

public class AvatarHandIK : MonoBehaviour
{
    [Header("Hand Rotation Offsets")]
    public Vector3 leftHandRotationOffset = new Vector3(-5f, 0f, 42f);
    public Vector3 rightHandRotationOffset = new Vector3(-5f, 0f, -42f);

    public Animator animator;
    public Transform vrLeftHandTarget;
    public Transform vrRightHandTarget;
    public float ikWeight = 1.0f;
    public Transform vrHeadTarget;

    public bool fingerTrackingEnabled = true;
    [Range(0f, 1f)] public float fingerTrackingWeight = 1f;
    public bool hideTrackedHandVisuals = true;
    public Transform leftFingerSourceRoot;
    public Transform rightFingerSourceRoot;

    [Header("Finger Curl Tuning")]
    public Vector3 fingerCurlAxis = Vector3.right;
    public float fingerCurlDirection = 1f;
    public Vector3 thumbCurlAxis = Vector3.right;
    public float thumbCurlDirection = 1f;
    public float leftThumbCurlDirection = 1f;
    public float openHandCorrectionDegrees = -35f;
    public float maxFingerCurlDegrees = 105f;
    public float maxThumbCurlDegrees = 70f;
    public float trackedCurlDegreesForFullFist = 60f;
    public float autoCalibrationSeconds = 1.5f;

    private FingerCurlMap[] leftFingerMaps;
    private FingerCurlMap[] rightFingerMaps;
    private bool fingerSourcesInitialized;
    private bool fingerAutoCalibrationStarted;
    private bool fingerPoseCalibrated;
    private float fingerAutoCalibrationEndTime;

    private struct FingerCurlMap
    {
        public HumanBodyBones ProximalBone;
        public HumanBodyBones IntermediateBone;
        public HumanBodyBones DistalBone;
        public string SourceA;
        public string SourceB;
        public string SourceC;
        public string SourceD;
        public bool IsThumb;

        public Transform ProximalTransform;
        public Transform IntermediateTransform;
        public Transform DistalTransform;
        public Transform SourceATransform;
        public Transform SourceBTransform;
        public Transform SourceCTransform;
        public Transform SourceDTransform;

        public Quaternion ProximalStartRotation;
        public Quaternion IntermediateStartRotation;
        public Quaternion DistalStartRotation;
        public float OpenCurl;

        public FingerCurlMap(string side, string finger, string sourcePrefix, bool isThumb)
        {
            ProximalBone = GetBone(side, finger + "Proximal");
            IntermediateBone = GetBone(side, finger + "Intermediate");
            DistalBone = GetBone(side, finger + "Distal");
            SourceA = "XRHand_" + sourcePrefix + (isThumb ? "Metacarpal" : "Proximal");
            SourceB = "XRHand_" + sourcePrefix + (isThumb ? "Proximal" : "Intermediate");
            SourceC = "XRHand_" + sourcePrefix + (isThumb ? "Distal" : "Distal");
            SourceD = "XRHand_" + sourcePrefix + "Tip";
            IsThumb = isThumb;

            ProximalTransform = null;
            IntermediateTransform = null;
            DistalTransform = null;
            SourceATransform = null;
            SourceBTransform = null;
            SourceCTransform = null;
            SourceDTransform = null;

            ProximalStartRotation = Quaternion.identity;
            IntermediateStartRotation = Quaternion.identity;
            DistalStartRotation = Quaternion.identity;
            OpenCurl = 0f;
        }
    }

    void Awake()
    {
        leftFingerMaps = CreateFingerMaps("Left");
        rightFingerMaps = CreateFingerMaps("Right");
    }

    void Start()
    {
        if (animator == null)
        {
            animator = GetComponent<Animator>();
        }

        if (animator == null)
        {
            enabled = false;
            return;
        }

        if (leftFingerSourceRoot == null)
        {
            GameObject leftHand = GameObject.Find("OpenXRLeftHand");
            leftFingerSourceRoot = leftHand != null ? leftHand.transform : null;
        }

        if (rightFingerSourceRoot == null)
        {
            GameObject rightHand = GameObject.Find("OpenXRRightHand");
            rightFingerSourceRoot = rightHand != null ? rightHand.transform : null;
        }

        if (hideTrackedHandVisuals)
        {
            HideHandVisuals(leftFingerSourceRoot);
            HideHandVisuals(rightFingerSourceRoot);
        }

        CacheAvatarFingerRestPose(leftFingerMaps);
        CacheAvatarFingerRestPose(rightFingerMaps);
    }

    void LateUpdate()
    {
        // Meta's HandVisual re-enables its renderer every Update() (_updateVisibility),
        // which undoes the one-shot hide in Start(). Re-hide after all Updates run so the
        // tracked hand mesh ("shadow hands") never flashes back on.
        if (hideTrackedHandVisuals)
        {
            HideHandVisuals(leftFingerSourceRoot);
            HideHandVisuals(rightFingerSourceRoot);
        }
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (animator == null) return;

        if (vrLeftHandTarget != null)
        {
            animator.SetIKPositionWeight(AvatarIKGoal.LeftHand, ikWeight);
            animator.SetIKRotationWeight(AvatarIKGoal.LeftHand, ikWeight);
            animator.SetIKPosition(AvatarIKGoal.LeftHand, vrLeftHandTarget.position);
            animator.SetIKRotation(AvatarIKGoal.LeftHand, ApplyRotationOffset(vrLeftHandTarget.rotation, leftHandRotationOffset));
        }

        if (vrRightHandTarget != null)
        {
            animator.SetIKPositionWeight(AvatarIKGoal.RightHand, ikWeight);
            animator.SetIKRotationWeight(AvatarIKGoal.RightHand, ikWeight);
            animator.SetIKPosition(AvatarIKGoal.RightHand, vrRightHandTarget.position);
            animator.SetIKRotation(AvatarIKGoal.RightHand, ApplyRotationOffset(vrRightHandTarget.rotation, rightHandRotationOffset));
        }

        if (fingerTrackingEnabled)
        {
            if (!fingerSourcesInitialized)
            {
                fingerSourcesInitialized = InitializeFingerMaps(leftFingerMaps, leftFingerSourceRoot) &&
                                           InitializeFingerMaps(rightFingerMaps, rightFingerSourceRoot);
            }

            if (fingerSourcesInitialized && !fingerPoseCalibrated)
            {
                AutoCalibrateOpenFingerCurl(leftFingerMaps);
                AutoCalibrateOpenFingerCurl(rightFingerMaps);
            }

            if (fingerPoseCalibrated)
            {
                ApplyFingerCurl(leftFingerMaps, isLeft: true);
                ApplyFingerCurl(rightFingerMaps, isLeft: false);
            }
        }

        animator.SetLookAtWeight(0f);
    }

    private FingerCurlMap[] CreateFingerMaps(string side)
    {
        return new[]
        {
            new FingerCurlMap(side, "Thumb", "Thumb", true),
            new FingerCurlMap(side, "Index", "Index", false),
            new FingerCurlMap(side, "Middle", "Middle", false),
            new FingerCurlMap(side, "Ring", "Ring", false),
            new FingerCurlMap(side, "Little", "Little", false),
        };
    }

    private static HumanBodyBones GetBone(string side, string fingerBone)
    {
        return (HumanBodyBones)System.Enum.Parse(typeof(HumanBodyBones), side + fingerBone);
    }

    private bool InitializeFingerMaps(FingerCurlMap[] maps, Transform sourceRoot)
    {
        if (sourceRoot == null) return false;

        for (int i = 0; i < maps.Length; i++)
        {
            maps[i].SourceATransform = FindChildByName(sourceRoot, maps[i].SourceA);
            maps[i].SourceBTransform = FindChildByName(sourceRoot, maps[i].SourceB);
            maps[i].SourceCTransform = FindChildByName(sourceRoot, maps[i].SourceC);
            maps[i].SourceDTransform = FindChildByName(sourceRoot, maps[i].SourceD);

            if (maps[i].ProximalTransform == null ||
                maps[i].IntermediateTransform == null ||
                maps[i].DistalTransform == null ||
                maps[i].SourceATransform == null ||
                maps[i].SourceBTransform == null ||
                maps[i].SourceCTransform == null ||
                maps[i].SourceDTransform == null)
            {
                return false;
            }

            maps[i].OpenCurl = MeasureCurl(maps[i]);
        }

        return true;
    }

    private void AutoCalibrateOpenFingerCurl(FingerCurlMap[] maps)
    {
        if (!fingerAutoCalibrationStarted)
        {
            fingerAutoCalibrationStarted = true;
            fingerAutoCalibrationEndTime = Time.time + autoCalibrationSeconds;
        }

        for (int i = 0; i < maps.Length; i++)
        {
            maps[i].OpenCurl = Mathf.Min(maps[i].OpenCurl, MeasureCurl(maps[i]));
        }

        if (Time.time >= fingerAutoCalibrationEndTime)
        {
            fingerPoseCalibrated = true;
            Debug.Log("Finger curl neutral pose auto-calibrated.");
        }
    }

    private void CacheAvatarFingerRestPose(FingerCurlMap[] maps)
    {
        for (int i = 0; i < maps.Length; i++)
        {
            maps[i].ProximalTransform = animator.GetBoneTransform(maps[i].ProximalBone);
            maps[i].IntermediateTransform = animator.GetBoneTransform(maps[i].IntermediateBone);
            maps[i].DistalTransform = animator.GetBoneTransform(maps[i].DistalBone);

            if (maps[i].ProximalTransform == null ||
                maps[i].IntermediateTransform == null ||
                maps[i].DistalTransform == null)
            {
                continue;
            }

            maps[i].ProximalStartRotation = maps[i].ProximalTransform.localRotation;
            maps[i].IntermediateStartRotation = maps[i].IntermediateTransform.localRotation;
            maps[i].DistalStartRotation = maps[i].DistalTransform.localRotation;
        }
    }

    private void ApplyFingerCurl(FingerCurlMap[] maps, bool isLeft)
    {
        Vector3 fAxis = fingerCurlAxis.sqrMagnitude > 0f ? fingerCurlAxis.normalized : Vector3.right;
        Vector3 tAxis = thumbCurlAxis.sqrMagnitude > 0f ? thumbCurlAxis.normalized : fAxis;

        for (int i = 0; i < maps.Length; i++)
        {
            if (maps[i].ProximalTransform == null ||
                maps[i].IntermediateTransform == null ||
                maps[i].DistalTransform == null ||
                maps[i].SourceATransform == null ||
                maps[i].SourceBTransform == null ||
                maps[i].SourceCTransform == null ||
                maps[i].SourceDTransform == null)
            {
                continue;
            }

            bool isThumb = maps[i].IsThumb;
            float rawCurl = Mathf.Max(0f, MeasureCurl(maps[i]) - maps[i].OpenCurl);
            float normalizedCurl = Mathf.Clamp01(rawCurl / trackedCurlDegreesForFullFist);
            float maxCurl = isThumb ? maxThumbCurlDegrees : maxFingerCurlDegrees;
            float direction = isThumb ? (isLeft ? leftThumbCurlDirection : thumbCurlDirection) : fingerCurlDirection;
            Vector3 axis = isThumb ? tAxis : fAxis;
            float curlDegrees = openHandCorrectionDegrees + (normalizedCurl * maxCurl * direction);

            SetFingerBone(maps[i].ProximalBone, maps[i].ProximalStartRotation, axis, curlDegrees * 0.45f);
            SetFingerBone(maps[i].IntermediateBone, maps[i].IntermediateStartRotation, axis, curlDegrees * 0.7f);
            SetFingerBone(maps[i].DistalBone, maps[i].DistalStartRotation, axis, curlDegrees * 0.45f);
        }
    }

    private float MeasureCurl(FingerCurlMap map)
    {
        Vector3 firstSegment = map.SourceBTransform.position - map.SourceATransform.position;
        Vector3 middleSegment = map.SourceCTransform.position - map.SourceBTransform.position;
        Vector3 lastSegment = map.SourceDTransform.position - map.SourceCTransform.position;


        if (firstSegment.sqrMagnitude < 0.000001f ||
            middleSegment.sqrMagnitude < 0.000001f ||
            lastSegment.sqrMagnitude < 0.000001f)
        {
            return 0f;
        }

        return Vector3.Angle(firstSegment, middleSegment) + Vector3.Angle(middleSegment, lastSegment);
    }

    private void SetFingerBone(HumanBodyBones bone, Quaternion startRotation, Vector3 axis, float degrees)
    {
        Quaternion targetRotation = startRotation * Quaternion.AngleAxis(degrees, axis);
        Quaternion currentRotation = animator.GetBoneTransform(bone).localRotation;
        animator.SetBoneLocalRotation(bone, Quaternion.Slerp(currentRotation, targetRotation, fingerTrackingWeight));
    }

    private Transform FindChildByName(Transform root, string childName)
    {
        foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
        {
            if (child.name == childName)
            {
                return child;
            }
        }

        return null;
    }

    private void HideHandVisuals(Transform handRoot)
    {
        if (handRoot == null) return;

        foreach (Renderer renderer in handRoot.GetComponentsInChildren<Renderer>(true))
        {
            renderer.enabled = false;
        }
    }

    private Quaternion ApplyRotationOffset(Quaternion sourceRotation, Vector3 offsetEuler)
    {
        return sourceRotation * Quaternion.Euler(offsetEuler);
    }
}

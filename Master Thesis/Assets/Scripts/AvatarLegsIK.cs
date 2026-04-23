using Unity.Mathematics;
using Unity.VisualScripting;
using UnityEngine;
using Kinect=Windows.Kinect;

public class AvatarLegsIK : MonoBehaviour
{
    public BodySourceManager BodySourceManager;
    private Windows.Kinect.Body trackedBody;

    public Transform leftLegIKTarget, rightLegIKTarget;
    public Transform leftKneeIKHint, rightKneeIKHint;
    public Transform avatarRoot;
    private Transform avatarHips;

void Start()
{
    Animator animator = GetComponent<Animator>();
    if (animator != null)
    {
        avatarHips = animator.GetBoneTransform(HumanBodyBones.Hips);
    }
    else
    {
        Debug.LogError("Animator component not found on this GameObject.");
    }
}

    void Update()
    {
        if (BodySourceManager == null)
        {
            Debug.LogError("BodySourceManager is not assigned!");
            return;
        }

        Kinect.Body[] data = BodySourceManager.GetData();
        if (data == null)
        {
            Debug.LogWarning("No Kinect data received.");
            return;
        }

        foreach (var body in data)
        {
            if (body != null && body.IsTracked)
            {
                trackedBody = body;
                break;
            }
        }

        if (trackedBody != null)
        {
            AlignAvatarWithKinect();
            UpdateIKTargets();
        }
    }


    void AlignAvatarWithKinect()
{

     if (trackedBody == null || avatarRoot == null) return;

    Vector3 leftFoot = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleLeft]);
    Vector3 rightFoot = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleRight]);

    Vector3 footCenter = (leftFoot + rightFoot) * 0.5f;
    footCenter.y = 0f; // Keep root grounded
}


// Updates the position of the IK targets based on Kinect tracking
void UpdateIKTargets()
{
    if (trackedBody == null) return;
    
    Vector3 kinectHipPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.SpineBase]);

    float hipYOffset = 1.0f; 
    Vector3 adjustedHipPos = kinectHipPos;

        adjustedHipPos = new Vector3(
            kinectHipPos.x,
            kinectHipPos.y + hipYOffset,
            kinectHipPos.z
        );
    Vector3 globalOffset = new Vector3(0, 0, 2.25f);

    transform.position = adjustedHipPos + globalOffset;

    // Kinect foot and knee positions
    Vector3 leftFootPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleLeft]);
    Vector3 rightFootPos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.AnkleRight]);
    Vector3 leftKneePos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.KneeLeft]);
    Vector3 rightKneePos = ConvertKinectToUnity(trackedBody.Joints[Kinect.JointType.KneeRight]);


    //Left foot rotation adjustment
    leftLegIKTarget.transform.localRotation = new Quaternion(leftLegIKTarget.transform.localRotation.x+90,leftLegIKTarget.transform.localRotation.y,leftLegIKTarget.transform.localRotation.z,leftLegIKTarget.transform.localRotation.w);


    // Apply offset to align with Meta tracking space
    Vector3 KneeOffset = new Vector3(0, 0f, 1.8f); // Knee offset
    Vector3 FeetOffset = new Vector3(0, 0.7f, 2.2f); // Feet offset
    leftFootPos += FeetOffset;
    rightFootPos += FeetOffset;
    leftKneePos += KneeOffset;
    rightKneePos += KneeOffset;

    if (leftLegIKTarget != null) leftLegIKTarget.position = Vector3.Lerp(leftLegIKTarget.position, leftFootPos, Time.deltaTime * 5f);
    if (rightLegIKTarget != null) rightLegIKTarget.position = Vector3.Lerp(rightLegIKTarget.position, rightFootPos, Time.deltaTime * 5f);

    // Calculate direction from foot to knee
    Vector3 leftKneeDir = (leftFootPos - leftKneePos).normalized;
    Vector3 rightKneeDir = (rightFootPos - rightKneePos).normalized;

    Vector3 forwardBias = avatarRoot.forward * 0.7f;  // Push hint forward
    Vector3 upwardBias = Vector3.up * 1.0f;          // Push hint upward

    // Calculate new knee hint positions to allow natural bending
    Vector3 leftHintPos = leftKneePos + leftKneeDir * 0.3f + forwardBias + upwardBias;
    Vector3 rightHintPos = rightKneePos + rightKneeDir * 0.3f + forwardBias + upwardBias;

    // Smooth movement for knee hints
    if (leftKneeIKHint != null) leftKneeIKHint.position = Vector3.Lerp(leftKneeIKHint.position, leftHintPos, Time.deltaTime * 5f);
    if (rightKneeIKHint != null) rightKneeIKHint.position = Vector3.Lerp(rightKneeIKHint.position, rightHintPos, Time.deltaTime * 5f);
}

    private Vector3 ConvertKinectToUnity(Kinect.Joint joint)
    {
        return new Vector3(joint.Position.X * 1f, joint.Position.Y * 1f, -joint.Position.Z * 1f);
    }
}

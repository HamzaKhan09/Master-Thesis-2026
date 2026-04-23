using UnityEngine;
using Kinect = Windows.Kinect;
using System.Collections.Generic; 


public class AvatarController : MonoBehaviour
{
    public BodySourceManager BodySourceManager;
    private Kinect.Body trackedBody;
    private Animator animator;

    public Transform vrHeadTarget;

    public float debug_x;

    public float debug_y;
    
    private Kinect.Body body;
    // Store last known bone rotations when Kinect loses tracking
    private Dictionary<Windows.Kinect.JointType, Quaternion> lastKnownRotations = new Dictionary<Windows.Kinect.JointType, Quaternion>();

    // Leg bone references
    private Transform spine, head;
    private Transform leftUpperLeg, leftLowerLeg, leftFoot;
    private Transform rightUpperLeg, rightLowerLeg, rightFoot;


    void Start()
{
    animator = GetComponent<Animator>();
    animator.applyRootMotion = false; // Allow external bone updates

    if (animator == null)
    {
        Debug.LogError("Animator component is missing!");
        return;
    }

    // Initialize bone transforms
    leftUpperLeg = animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
    leftLowerLeg = animator.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
    leftFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);

    rightUpperLeg = animator.GetBoneTransform(HumanBodyBones.RightUpperLeg);
    rightLowerLeg = animator.GetBoneTransform(HumanBodyBones.RightLowerLeg);
    rightFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);

    // Set a default position to avoid floating at start
    transform.position = new Vector3(0, 0, 0); // Start slightly in front of Kinect
    transform.rotation = Quaternion.Euler(0, 0, 0); // Ensure correct facing direction
    
    if (leftUpperLeg == null) Debug.LogError("Left Upper Leg bone is null!");
    if (rightUpperLeg == null) Debug.LogError("Right Upper Leg bone is null!");
    if (rightFoot == null) Debug.LogError("Right foot bone is null!");
    if (leftFoot == null) Debug.LogError("Left foot bone is null!");
    if (leftLowerLeg == null) Debug.LogError("Left lower Leg bone is null!");
    if (rightLowerLeg == null) Debug.LogError("Right lower Leg bone is null!");

}



   void Update()
{

    Debug.Log("AvatarController Update is running.");

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
        MapJointsToAvatar();

        Vector3 footRight = ConvertKinectToUnity(trackedBody.Joints[Windows.Kinect.JointType.FootRight]);
        Vector3 footLeft = ConvertKinectToUnity(trackedBody.Joints[Windows.Kinect.JointType.FootLeft]);

        Debug.Log($"FootRight Position: {footRight}");
        Debug.Log($"FootLeft Position: {footLeft}");

    }
}



    // void LateUpdate()
    // {
    //     if (vrHeadTarget != null)
    //     {
    //         // Match avatar root to head position (optionally with vertical offset)
    //         Vector3 headPos = vrHeadTarget.position;
    //         headPos.y = 0; // keep it grounded
    //         transform.position = Vector3.Lerp(transform.position, headPos, Time.deltaTime * 5f);
    //     }
    // }

private void AlignAvatarWithKinect()
{

    if (trackedBody == null) return; // Prevents errors when Kinect loses tracking

    Vector3 spineBase = ConvertKinectToUnity(trackedBody.Joints[Windows.Kinect.JointType.SpineBase]);

    spineBase.y = 0.0f;

    Vector3 hipLeft = ConvertKinectToUnity(trackedBody.Joints[Windows.Kinect.JointType.HipLeft]);
    Vector3 hipRight = ConvertKinectToUnity(trackedBody.Joints[Windows.Kinect.JointType.HipRight]);

    Vector3 forward = (hipRight - hipLeft).normalized;
    if (forward != Vector3.zero)
    {
        transform.rotation = Quaternion.LookRotation(forward, Vector3.up);
    }

   
    // Rotation Offset
    // transform.rotation *= Quaternion.Euler(0, -90, 0);

    // Right Leg Position
    // rightUpperLeg.position = new Vector3(rightUpperLeg.position.x, 0.9f, rightUpperLeg.position.z); // Force leg lower
}



private void MapJointsToAvatar()
{
    // float smoothFactor = 5f; //smoother motion

    //Spine and Head
    // spine.rotation = Quaternion.Slerp(spine.rotation, GetKinectBoneRotation(Windows.Kinect.JointType.SpineMid, Windows.Kinect.JointType.Head), Time.deltaTime * smoothFactor);
    //head.rotation = Quaternion.Slerp(head.rotation, GetKinectBoneRotation(Windows.Kinect.JointType.Head, Windows.Kinect.JointType.SpineMid), Time.deltaTime * smoothFactor);
    
    // Map Left Leg
    leftUpperLeg.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.HipLeft, Windows.Kinect.JointType.KneeLeft);
    leftLowerLeg.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.KneeLeft, Windows.Kinect.JointType.AnkleLeft);
    leftFoot.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.AnkleLeft, Windows.Kinect.JointType.FootLeft);

    // Map Right Leg
    rightUpperLeg.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.HipRight, Windows.Kinect.JointType.KneeRight);
    rightLowerLeg.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.KneeRight, Windows.Kinect.JointType.AnkleRight);
    rightFoot.rotation = GetKinectBoneRotation(Windows.Kinect.JointType.AnkleRight, Windows.Kinect.JointType.FootRight);

}




private Quaternion GetKinectBoneRotation(Windows.Kinect.JointType startJoint, Windows.Kinect.JointType endJoint)
{
    if (trackedBody.Joints[startJoint].TrackingState == Kinect.TrackingState.NotTracked ||
        trackedBody.Joints[endJoint].TrackingState == Kinect.TrackingState.NotTracked)
    {
        return Quaternion.identity;
    }

    Vector3 start = ConvertKinectToUnity(trackedBody.Joints[startJoint]);
    Vector3 end = ConvertKinectToUnity(trackedBody.Joints[endJoint]);

    Vector3 direction = (end - start).normalized;

    if (direction == Vector3.zero) return Quaternion.identity;

    Quaternion newRotation = Quaternion.LookRotation(direction, Vector3.up);

     // Left Foot Flipping Issue**
    if (startJoint == Windows.Kinect.JointType.AnkleLeft)
    {
        newRotation *= Quaternion.Euler(0, 180, 180); // Inverts  left foot correctly
    }

    // // // Apply different rotation fixes for each leg
    if (startJoint == Windows.Kinect.JointType.HipRight || startJoint == Windows.Kinect.JointType.KneeRight)
    {
        newRotation *= Quaternion.Euler(90, 0, 180); // right leg
    }
    else if (startJoint == Windows.Kinect.JointType.HipLeft || startJoint == Windows.Kinect.JointType.KneeLeft)
    {
        newRotation *= Quaternion.Euler(90, 0, 180); // left leg 
    }

    lastKnownRotations[startJoint] = newRotation;
    return newRotation;
    
}


private Vector3 ConvertKinectToUnity(Windows.Kinect.Joint joint)
{
    // Example adjustment for proper scaling/alignment
    return new Vector3(
        joint.Position.X * 5f, 
        joint.Position.Y * 5f, 
        -joint.Position.Z * 5f // Flip Z-axis
    );
}


}

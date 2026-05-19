using UnityEngine;
using Kinect = Windows.Kinect;

public class AvatarLegsIK : MonoBehaviour
{
    public BodySourceManager BodySourceManager;
    private Kinect.Body trackedBody;

    public Transform leftLegIKTarget, rightLegIKTarget;
    public Transform leftKneeIKHint, rightKneeIKHint;
    public Transform avatarRoot;

    void Update()
    {
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

    private Vector3 ConvertKinectToUnity(Kinect.Joint joint)
    {
        return new Vector3(joint.Position.X, joint.Position.Y, -joint.Position.Z);
    }
}

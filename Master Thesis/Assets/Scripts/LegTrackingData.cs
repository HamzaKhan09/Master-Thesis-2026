using UnityEngine;
using Kinect = Windows.Kinect;

public class LegTrackingData
{
    public Vector3 LeftHip { get; private set; }
    public Vector3 LeftKnee { get; private set; }
    public Vector3 LeftAnkle { get; private set; }
    public Vector3 LeftFoot { get; private set; }

    public Vector3 RightHip { get; private set; }
    public Vector3 RightKnee { get; private set; }
    public Vector3 RightAnkle { get; private set; }
    public Vector3 RightFoot { get; private set; }

    public void UpdateLegData(Kinect.Body body)
    {
        LeftHip = GetVector3FromJoint(body.Joints[Kinect.JointType.HipLeft]);
        LeftKnee = GetVector3FromJoint(body.Joints[Kinect.JointType.KneeLeft]);
        LeftAnkle = GetVector3FromJoint(body.Joints[Kinect.JointType.AnkleLeft]);
        LeftFoot = GetVector3FromJoint(body.Joints[Kinect.JointType.FootLeft]);

        RightHip = GetVector3FromJoint(body.Joints[Kinect.JointType.HipRight]);
        RightKnee = GetVector3FromJoint(body.Joints[Kinect.JointType.KneeRight]);
        RightAnkle = GetVector3FromJoint(body.Joints[Kinect.JointType.AnkleRight]);
        RightFoot = GetVector3FromJoint(body.Joints[Kinect.JointType.FootRight]);
    }

    private Vector3 GetVector3FromJoint(Kinect.Joint joint)
    {
        return new Vector3(joint.Position.X *5, joint.Position.Y *5, -joint.Position.Z *5);
    }
}

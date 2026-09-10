using System;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

// Bridges OptiTrack skeleton data into the same UDP JSON contract MediaPipePoseReceiver
// already consumes, so the OptiTrack condition can reuse MediaPipePoseReceiver/AvatarLegsIK
// unmodified — same "one sender per source, one shared receiver contract" pattern already
// used for the MeTRAbs detector. Point a second MediaPipePoseReceiver (different port) at
// this sender's targetPort to wire it up.
public class OptitrackLegPoseUdpSender : MonoBehaviour
{
    [Header("OptiTrack Source")]
    public OptitrackStreamingClient streamingClient;
    [Tooltip("Must match the Skeleton Asset Name configured in Motive.")]
    public string skeletonAssetName = "Skeleton";

    [Header("UDP Target")]
    [Tooltip("Port the receiving MediaPipePoseReceiver instance is listening on for this condition. Use a different port than the webcam/MeTRAbs receivers.")]
    public int targetPort = 5057;
    public string targetAddress = "127.0.0.1";

    [Header("Send Rate")]
    [Tooltip("0 = send every Update().")]
    public float sendIntervalSeconds = 0f;

    private UdpClient udpClient;
    private OptitrackSkeletonDefinition skeletonDef;
    private int leftHipBoneId = -1, rightHipBoneId = -1;
    private int leftKneeBoneId = -1, rightKneeBoneId = -1;
    private int leftAnkleBoneId = -1, rightAnkleBoneId = -1;
    private bool boneIdsResolved;
    private float nextSendTime;

    // Field names must exactly match MediaPipePoseReceiver's private PosePacket/PoseLandmark
    // classes — JsonUtility serializes by field name, not by type identity.
    [Serializable]
    private class PoseLandmark
    {
        public string name;
        public float x;
        public float y;
        public float z;
        public float visibility;
        public float image_x;
        public float image_y;
    }

    [Serializable]
    private class PosePacket
    {
        public double timestamp;
        public bool tracked;
        public string coordinate_space;
        public PoseLandmark[] landmarks;
    }

    void Start()
    {
        if (streamingClient == null)
        {
            streamingClient = OptitrackStreamingClient.FindDefaultClient();
        }

        if (streamingClient == null)
        {
            Debug.LogError($"{nameof(OptitrackLegPoseUdpSender)}: no OptitrackStreamingClient found/assigned; disabling.", this);
            enabled = false;
            return;
        }

        if (streamingClient.SkeletonCoordinates != StreamingCoordinatesValues.Global)
        {
            Debug.LogWarning($"{nameof(OptitrackLegPoseUdpSender)}: StreamingClient.SkeletonCoordinates is not set to Global — bone positions will be parent-relative, not room-space. Set it to Global in the Inspector.", this);
        }

        streamingClient.RegisterSkeleton(this, skeletonAssetName);
        udpClient = new UdpClient();
        udpClient.Connect(targetAddress, targetPort);

        Debug.Log($"OptiTrack leg pose sender streaming skeleton \"{skeletonAssetName}\" to {targetAddress}:{targetPort}.");
    }

    void Update()
    {
        if (!boneIdsResolved && !ResolveBoneIds())
        {
            return;
        }

        if (sendIntervalSeconds > 0f && Time.time < nextSendTime)
        {
            return;
        }
        nextSendTime = Time.time + sendIntervalSeconds;

        OptitrackSkeletonState skelState = streamingClient.GetLatestSkeletonState(skeletonDef.Id);

        PosePacket packet = new PosePacket
        {
            timestamp = Time.realtimeSinceStartupAsDouble,
            coordinate_space = "world",
            tracked = skelState != null,
            landmarks = skelState == null ? Array.Empty<PoseLandmark>() : new[]
            {
                MakeLandmark("left_hip", skelState, leftHipBoneId),
                MakeLandmark("right_hip", skelState, rightHipBoneId),
                MakeLandmark("left_knee", skelState, leftKneeBoneId),
                MakeLandmark("right_knee", skelState, rightKneeBoneId),
                MakeLandmark("left_ankle", skelState, leftAnkleBoneId),
                MakeLandmark("right_ankle", skelState, rightAnkleBoneId),
            },
        };

        string json = JsonUtility.ToJson(packet);
        byte[] bytes = Encoding.UTF8.GetBytes(json);
        udpClient.Send(bytes, bytes.Length);
    }

    private PoseLandmark MakeLandmark(string name, OptitrackSkeletonState skelState, int boneId)
    {
        // Mirrors OptitrackSkeletonAnimator's own lookup: with SkeletonCoordinates set to
        // Global, room-space poses come from LocalBonePoses — the plugin's field naming is
        // inverted relative to what you'd expect from the enum name.
        if (!skelState.LocalBonePoses.TryGetValue(boneId, out OptitrackPose pose))
        {
            return new PoseLandmark { name = name, visibility = 0f };
        }

        return new PoseLandmark
        {
            name = name,
            x = pose.Position.x,
            y = pose.Position.y,
            z = pose.Position.z,
            visibility = 1f,
        };
    }

    private bool ResolveBoneIds()
    {
        skeletonDef = streamingClient.GetSkeletonDefinitionByName(skeletonAssetName);
        if (skeletonDef == null)
        {
            return false;
        }

        leftHipBoneId = FindBoneId("_LThigh");
        rightHipBoneId = FindBoneId("_RThigh");
        leftKneeBoneId = FindBoneId("_LShin");
        rightKneeBoneId = FindBoneId("_RShin");
        leftAnkleBoneId = FindBoneId("_LFoot");
        rightAnkleBoneId = FindBoneId("_RFoot");

        if (leftHipBoneId < 0 || rightHipBoneId < 0 || leftKneeBoneId < 0 ||
            rightKneeBoneId < 0 || leftAnkleBoneId < 0 || rightAnkleBoneId < 0)
        {
            Debug.LogError($"{nameof(OptitrackLegPoseUdpSender)}: could not resolve all six leg bone names in skeleton \"{skeletonAssetName}\" — check the Motive bone naming convention/skeleton definition.", this);
            return false;
        }

        boneIdsResolved = true;
        return true;
    }

    private int FindBoneId(string suffix)
    {
        string boneName = skeletonAssetName + suffix;
        for (int i = 0; i < skeletonDef.Bones.Count; i++)
        {
            if (skeletonDef.Bones[i].Name == boneName)
            {
                return skeletonDef.Bones[i].Id;
            }
        }
        return -1;
    }

    void OnDestroy()
    {
        udpClient?.Close();
    }
}

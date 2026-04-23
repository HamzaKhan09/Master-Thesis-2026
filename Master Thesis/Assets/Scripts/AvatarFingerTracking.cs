using UnityEngine;
using System.Collections.Generic;

public class AvatarFingerTracking : MonoBehaviour
{
    public OVRSkeleton ovrSkeleton;
    public Transform[] avatarFingerJoints; // Assign this manually in Inspector

    private List<OVRBone> bones;

    void Start()
    {
        if (ovrSkeleton == null)
        {
            Debug.LogError("OVRSkeleton not assigned!");
            return;
        }

        bones = new List<OVRBone>(ovrSkeleton.Bones);
    }

    void Update()
    {
        if (bones == null || avatarFingerJoints == null || bones.Count != avatarFingerJoints.Length)
            return;

        for (int i = 0; i < avatarFingerJoints.Length; i++)
        {
            avatarFingerJoints[i].position = bones[i].Transform.position;
            avatarFingerJoints[i].rotation = bones[i].Transform.rotation;
        }
    }
}

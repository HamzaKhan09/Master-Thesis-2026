using UnityEngine;
using Oculus.Interaction;

public class HandTrackingMapper : MonoBehaviour
{
    [SerializeField] private OVRHand _ovrHand; // Assign Left/Right OVRHand in Inspector
    [SerializeField] private SkinnedMeshRenderer _avatarHand; // Assign avatar's hand renderer

    // Map Oculus bone IDs to avatar bone names
    [System.Serializable]
    public class BoneMap
    {
        public OVRSkeleton.BoneId OculusBoneId;
        public string AvatarBoneName;
    }

    [SerializeField] private BoneMap[] _boneMappings;

    private Transform[] _avatarBones;

    void Start()
    {
        // Cache avatar bone transforms
        _avatarBones = new Transform[_boneMappings.Length];
        for (int i = 0; i < _boneMappings.Length; i++)
        {
            _avatarBones[i] = FindBoneTransform(_avatarHand, _boneMappings[i].AvatarBoneName);
        }
    }

    void LateUpdate()
    {
        if (_ovrHand.IsTracked)
        {
            var skeleton = _ovrHand.GetComponent<OVRSkeleton>();
            if (skeleton != null)
            {
                foreach (var bone in skeleton.Bones)
                {
                    for (int i = 0; i < _boneMappings.Length; i++)
                    {
                        if (bone.Id == _boneMappings[i].OculusBoneId && _avatarBones[i] != null)
                        {
                            _avatarBones[i].rotation = bone.Transform.rotation;
                            break;
                        }
                    }
                }
            }
        }
    }

    private Transform FindBoneTransform(SkinnedMeshRenderer renderer, string boneName)
    {
        foreach (Transform bone in renderer.bones)
        {
            if (bone.name.Equals(boneName))
                return bone;
        }
        return null;
    }
}
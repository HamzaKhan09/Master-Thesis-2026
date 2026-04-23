using UnityEngine;
using System.Collections.Generic;
using Kinect = Windows.Kinect;

public class BodySourceView : MonoBehaviour
{
    public GameObject BodySourceManager;

    // Prefab for visualizing joints
    public GameObject JointPrefab;

    private Dictionary<ulong, GameObject> _BodyObjects = new Dictionary<ulong, GameObject>(); // For visualizing joints
    private Dictionary<ulong, LegTrackingData> _LegData = new Dictionary<ulong, LegTrackingData>(); // For storing leg tracking data
    private BodySourceManager _BodyManager;

    void Update()
    {
        if (BodySourceManager == null)
        {
            return;
        }

        _BodyManager = BodySourceManager.GetComponent<BodySourceManager>();
        if (_BodyManager == null)
        {
            return;
        }

        Kinect.Body[] data = _BodyManager.GetData();
        if (data == null)
        {
            return;
        }

        List<ulong> trackedIds = new List<ulong>();
        foreach (var body in data)
        {
            if (body == null || !body.IsTracked)
            {
                continue;
            }

            trackedIds.Add(body.TrackingId);

            // Create visual objects for new bodies
            if (!_BodyObjects.ContainsKey(body.TrackingId))
            {
                _BodyObjects[body.TrackingId] = CreateBodyObject(body.TrackingId);
                _LegData[body.TrackingId] = new LegTrackingData();
            }

            // Update leg tracking data
            _LegData[body.TrackingId].UpdateLegData(body);

            // Update visual objects for the body
            RefreshBodyObject(body, _BodyObjects[body.TrackingId]);
        }

        // Remove untracked bodies
        List<ulong> knownIds = new List<ulong>(_BodyObjects.Keys);
        foreach (ulong trackingId in knownIds)
        {
            if (!trackedIds.Contains(trackingId))
            {
                Destroy(_BodyObjects[trackingId]); // Destroy visual objects
                _BodyObjects.Remove(trackingId);
                _LegData.Remove(trackingId); // Remove leg data
            }
        }
    }

    private GameObject CreateBodyObject(ulong id)
    {
        GameObject body = new GameObject("Body:" + id);

        // Create joints for legs only
        foreach (Kinect.JointType jt in new Kinect.JointType[]
        {
            Kinect.JointType.HipLeft,
            Kinect.JointType.KneeLeft,
            Kinect.JointType.AnkleLeft,
            Kinect.JointType.FootLeft,
            Kinect.JointType.HipRight,
            Kinect.JointType.KneeRight,
            Kinect.JointType.AnkleRight,
            Kinect.JointType.FootRight
        })
        {
            GameObject jointObj = Instantiate(JointPrefab);
            jointObj.name = jt.ToString();
            jointObj.transform.parent = body.transform;
        }

        return body;
    }

    private void RefreshBodyObject(Kinect.Body body, GameObject bodyObject)
    {
        foreach (Kinect.JointType jt in new Kinect.JointType[]
        {
            Kinect.JointType.HipLeft,
            Kinect.JointType.KneeLeft,
            Kinect.JointType.AnkleLeft,
            Kinect.JointType.FootLeft,
            Kinect.JointType.HipRight,
            Kinect.JointType.KneeRight,
            Kinect.JointType.AnkleRight,
            Kinect.JointType.FootRight
        })
        {
            Kinect.Joint joint = body.Joints[jt];
            Transform jointObj = bodyObject.transform.Find(jt.ToString());

            if (joint.TrackingState == Kinect.TrackingState.Tracked)
            {
                jointObj.gameObject.SetActive(true);
                jointObj.position = GetVector3FromJoint(joint); // Update joint position
            }
            else
            {
                jointObj.gameObject.SetActive(false); // Hide joint if not tracked
            }
        }
    }

    private Vector3 GetVector3FromJoint(Kinect.Joint joint)
    {
        return new Vector3(joint.Position.X * 2, joint.Position.Y * 2, -joint.Position.Z * 2);
    }

    // Public method to get leg tracking data
    public LegTrackingData GetLegData(ulong trackingId)
    {
        if (_LegData.ContainsKey(trackingId))
        {
            return _LegData[trackingId];
        }
        return null; // No data found for this tracking ID
    }

    // Public method to get all tracked IDs
    public List<ulong> GetTrackedIds()
    {
        return new List<ulong>(_LegData.Keys);
    }
}

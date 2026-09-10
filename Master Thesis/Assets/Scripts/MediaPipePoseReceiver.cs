using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

public class MediaPipePoseReceiver : MonoBehaviour
{
    [Header("UDP")]
    public int port = 5055;

    [Header("Debug Spheres")]
    public bool createDebugSpheres = true;
    public float sphereSize = 0.08f;
    public Material sphereMaterial;

    [Header("Coordinate Mapping")]
    public bool centerOnHipMidpoint = true;
    public bool followImageBodyPosition = true;
    public bool followImageBodyHeight = true;
    public bool estimateDepthFromHipWidth = true;
    public bool swapLeftRight = false;
    public bool mirrorX = false;
    public bool invertY = false;
    public bool invertZ = true;
    public float horizontalScale = 1f;
    public float verticalScale = 1f;
    public float depthScale = 0.6f;
    [Tooltip("Counter-rotates the landmark cloud around the hip midpoint to cancel the webcam's up/down tilt. Positive brings the ankles forward. Tune in Play mode until the ankle spheres sit vertically under the hip spheres, then set the value in Edit mode and save the scene.")]
    public float pitchCorrectionDegrees = 0f;
    public float imageRootHorizontalScale = 3f;
    public float imageRootVerticalScale = 2f;
    public float imageRootDepthScale = 0.75f;
    public float maxImageRootDepthOffset = 1f;
    public float maxImageRootHeightOffset = 1f;
    public float referenceHipImageWidth = 0.18f;
    public float referenceHipImageY = 0.55f;
    public Vector3 positionOffset = new Vector3(0f, 0f, 2f);
    public float smoothing = 12f;
    [Range(0f, 1f)] public float minimumVisibility = 0.5f;
    [Tooltip("If no new UDP packet arrives within this many seconds, isTracking drops to false so consumers stop acting on stale data.")]
    public float packetTimeoutSeconds = 0.5f;
    public bool logDepthEstimate = false;
    public float depthLogInterval = 1f;
    [Tooltip("Logs the raw JSON of the most recent UDP packet so it can be compared against the sender's console output.")]
    public bool logReceivedPackets = true;
    public float packetLogInterval = 2f;

    [HideInInspector] public bool isTracking;

    public Transform leftHip;
    public Transform rightHip;
    public Transform leftKnee;
    public Transform rightKnee;
    public Transform leftAnkle;
    public Transform rightAnkle;

    private UdpClient udpClient;
    private Thread receiveThread;
    private volatile bool isRunning;
    private readonly object packetLock = new object();
    private PosePacket latestPacket;
    private bool hasPacket;
    private string pendingWarning;
    private float nextDepthLogTime;
    private volatile int packetCounter;
    private int lastSeenPacketCounter = -1;
    private float lastPacketTime = float.NegativeInfinity;
    private bool staleWarningIssued;
    private float nextPacketLogTime;

    [Serializable]
    private class PosePacket
    {
        public double timestamp;
        public bool tracked;
        public string coordinate_space;
        public PoseLandmark[] landmarks;
    }

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

    void Start()
    {
        if (createDebugSpheres)
        {
            leftHip = EnsureDebugSphere(leftHip, "MediaPipe Left Hip");
            rightHip = EnsureDebugSphere(rightHip, "MediaPipe Right Hip");
            leftKnee = EnsureDebugSphere(leftKnee, "MediaPipe Left Knee");
            rightKnee = EnsureDebugSphere(rightKnee, "MediaPipe Right Knee");
            leftAnkle = EnsureDebugSphere(leftAnkle, "MediaPipe Left Ankle");
            rightAnkle = EnsureDebugSphere(rightAnkle, "MediaPipe Right Ankle");
        }

        udpClient = new UdpClient(port);
        isRunning = true;
        receiveThread = new Thread(ReceiveLoop)
        {
            IsBackground = true
        };
        receiveThread.Start();

        Debug.Log($"MediaPipe pose receiver listening on UDP port {port}.");
    }

    void Update()
    {
        PosePacket packet = null;
        lock (packetLock)
        {
            if (hasPacket)
            {
                packet = latestPacket;
            }
        }

        // Staleness watchdog: a parse failure or a stalled sender leaves latestPacket
        // frozen at the last good frame while everything downstream keeps trusting it.
        // Only fresh packets count as tracking.
        if (packetCounter != lastSeenPacketCounter)
        {
            lastSeenPacketCounter = packetCounter;
            lastPacketTime = Time.time;
            staleWarningIssued = false;
        }

        if (logReceivedPackets && packet != null && Time.time >= nextPacketLogTime)
        {
            nextPacketLogTime = Time.time + packetLogInterval;

            if (packet.tracked && packet.landmarks != null)
            {
                StringBuilder received = new StringBuilder("received: ");
                for (int i = 0; i < packet.landmarks.Length; i++)
                {
                    PoseLandmark lm = packet.landmarks[i];
                    if (i > 0)
                    {
                        received.Append(" | ");
                    }
                    received.Append($"{lm.name} ({lm.x:F3}, {lm.y:F3}, {lm.z:F3})");
                }
                Debug.Log(received.ToString()); //target logs
            }
            else
            {
                Debug.Log("received: not tracked"); //target logs
            }
        }

        bool packetsStale = Time.time - lastPacketTime > packetTimeoutSeconds;
        if (packetsStale && !staleWarningIssued && packet != null)
        {
            staleWarningIssued = true;
            Debug.LogWarning("MediaPipe packets stopped arriving (sender stalled or packets unparseable) — tracking paused.");
        }

        if (packet == null || packetsStale || !packet.tracked || packet.landmarks == null)
        {
            isTracking = false;
            FlushPendingWarning();
            return;
        }

        isTracking = true;

        for (int i = 0; i < packet.landmarks.Length; i++)
        {
            PoseLandmark landmark = packet.landmarks[i];
            if (landmark.visibility < minimumVisibility)
            {
                continue;
            }

            Transform target = GetTarget(landmark.name);
            if (target == null)
            {
                continue;
            }
    
            Vector3 referencePosition = centerOnHipMidpoint ? GetHipMidpoint(packet) : Vector3.zero;
            Vector3 rootOffset = followImageBodyPosition ? GetImageBodyRootOffset(packet) : Vector3.zero;
            Vector3 targetPosition = ConvertMediaPipeToUnity(landmark, packet.coordinate_space, referencePosition, rootOffset);
            MoveTarget(target, landmark, targetPosition);
        }

        FlushPendingWarning();
    }

    void OnDestroy()
    {
        StopReceiver();
    }

    void OnApplicationQuit()
    {
        StopReceiver();
    }

    private void ReceiveLoop()
    {
        IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, 0);

        while (isRunning)
        {
            try
            {
                byte[] data = udpClient.Receive(ref remoteEndPoint);
                string json = Encoding.UTF8.GetString(data);
                PosePacket packet = JsonUtility.FromJson<PosePacket>(json);

                lock (packetLock)
                {
                    latestPacket = packet;
                    hasPacket = true;
                }
                packetCounter++;
            }
            catch (SocketException)
            {
                if (isRunning)
                {
                    SetPendingWarning("MediaPipe UDP receiver socket stopped unexpectedly.");
                }
            }
            catch (Exception exception)
            {
                SetPendingWarning($"MediaPipe UDP packet ignored: {exception.Message}");
            }
        }
    }

    private void SetPendingWarning(string message)
    {
        lock (packetLock)
        {
            pendingWarning = message;
        }
    }

    private void FlushPendingWarning()
    {
        string warning = null;
        lock (packetLock)
        {
            if (!string.IsNullOrEmpty(pendingWarning))
            {
                warning = pendingWarning;
                pendingWarning = null;
            }
        }

        if (!string.IsNullOrEmpty(warning))
        {
            Debug.LogWarning(warning);
        }
    }

    private void StopReceiver()
    {
        isRunning = false;

        if (udpClient != null)
        {
            udpClient.Close();
            udpClient = null;
        }

        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Join(100);
            receiveThread = null;
        }
    }

    private Transform EnsureDebugSphere(Transform existingTransform, string objectName)
    {
        if (existingTransform != null)
        {
            return existingTransform;
        }

        GameObject sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        sphere.name = objectName;
        sphere.transform.SetParent(transform, false);
        sphere.transform.localScale = Vector3.one * sphereSize;

        if (sphereMaterial != null)
        {
            Renderer renderer = sphere.GetComponent<Renderer>();
            renderer.material = sphereMaterial;
        }

        // These GameObjects are IK position targets consumed by AvatarLegsIK, not just
        // visual debug aids — keep them, but hide the mesh so they don't render in-game.
        sphere.GetComponent<Renderer>().enabled = false;

        return sphere.transform;
    }

    private Transform GetTarget(string landmarkName)
    {
        if (swapLeftRight)
        {
            landmarkName = SwapLandmarkSide(landmarkName);
        }

        switch (landmarkName)
        {
            case "left_hip": return leftHip;
            case "right_hip": return rightHip;
            case "left_knee": return leftKnee;
            case "right_knee": return rightKnee;
            case "left_ankle": return leftAnkle;
            case "right_ankle": return rightAnkle;
            default: return null;
        }
    }

    private string SwapLandmarkSide(string landmarkName)
    {
        if (landmarkName.StartsWith("left_"))
        {
            return "right_" + landmarkName.Substring(5);
        }

        if (landmarkName.StartsWith("right_"))
        {
            return "left_" + landmarkName.Substring(6);
        }

        return landmarkName;
    }

    private Vector3 GetHipMidpoint(PosePacket packet)
    {
        PoseLandmark left = FindLandmark(packet, "left_hip");
        PoseLandmark right = FindLandmark(packet, "right_hip");

        if (left == null || right == null)
        {
            return Vector3.zero;
        }

        return new Vector3(
            (left.x + right.x) * 0.5f,
            (left.y + right.y) * 0.5f,
            (left.z + right.z) * 0.5f);
    }

    private PoseLandmark FindLandmark(PosePacket packet, string landmarkName)
    {
        for (int i = 0; i < packet.landmarks.Length; i++)
        {
            if (packet.landmarks[i].name == landmarkName)
            {
                return packet.landmarks[i];
            }
        }

        return null;
    }

    private void MoveTarget(Transform target, PoseLandmark landmark, Vector3 targetPosition)
    {
        if (target == null || landmark.visibility < minimumVisibility)
        {
            return;
        }

        float blend = 1f - Mathf.Exp(-smoothing * Time.deltaTime);
        target.position = Vector3.Lerp(target.position, targetPosition, blend);
    }

    private Vector3 GetImageBodyRootOffset(PosePacket packet)
    {
        PoseLandmark left = FindLandmark(packet, "left_hip");
        PoseLandmark right = FindLandmark(packet, "right_hip");

        if (left == null || right == null)
        {
            return Vector3.zero;
        }

        float hipMidX = (left.image_x + right.image_x) * 0.5f;
        float hipMidY = (left.image_y + right.image_y) * 0.5f;
        float hipImageWidth = Mathf.Abs(left.image_x - right.image_x);

        float rootX = (hipMidX - 0.5f) * imageRootHorizontalScale;
        float rootY = 0f;
        float rootZ = 0f;

        if (followImageBodyHeight)
        {
            rootY = (referenceHipImageY - hipMidY) * imageRootVerticalScale;
            rootY = Mathf.Clamp(rootY, -maxImageRootHeightOffset, maxImageRootHeightOffset);
        }

        if (estimateDepthFromHipWidth && hipImageWidth > 0.001f)
        {
            rootZ = ((referenceHipImageWidth / hipImageWidth) - 1f) * imageRootDepthScale;
            rootZ = Mathf.Clamp(rootZ, -maxImageRootDepthOffset, maxImageRootDepthOffset);
        }

        if (logDepthEstimate && Time.time >= nextDepthLogTime)
        {
            nextDepthLogTime = Time.time + depthLogInterval;
            Debug.Log($"MediaPipe depth estimate | hip width {hipImageWidth:F3}, rootY {rootY:F2}, rootZ {rootZ:F2}, reference width {referenceHipImageWidth:F3}, reference Y {referenceHipImageY:F3}");
        }

        if (mirrorX)
        {
            rootX = -rootX;
        }

        return new Vector3(rootX, rootY, rootZ);
    }

    private Vector3 ConvertMediaPipeToUnity(PoseLandmark landmark, string coordinateSpace, Vector3 referencePosition, Vector3 rootOffset)
    {
        bool isWorldSpace = coordinateSpace == "world";
        float sourceX = landmark.x - referencePosition.x;
        float sourceY = landmark.y - referencePosition.y;
        float sourceZ = landmark.z - referencePosition.z;

        float unityX = sourceX * horizontalScale;
        float unityY = (isWorldSpace ? sourceY : -sourceY) * verticalScale;
        float unityZ = sourceZ * depthScale;

        if (mirrorX)
        {
            unityX = -unityX;
        }

        if (invertY)
        {
            unityY = -unityY;
        }

        if (invertZ)
        {
            unityZ = -unityZ;
        }

        Vector3 unityPosition = new Vector3(unityX, unityY, unityZ);

        // The vector is hip-relative here (centerOnHipMidpoint), so this rotates the
        // whole point cloud around the hips: the hip spheres stay put and points below
        // the hips swing forward, cancelling the camera-tilt slant.
        if (Mathf.Abs(pitchCorrectionDegrees) > 0.01f)
        {
            unityPosition = Quaternion.Euler(-pitchCorrectionDegrees, 0f, 0f) * unityPosition;
        }

        return unityPosition + rootOffset + positionOffset;
    }
}

using UnityEngine;

public class VRRootFollower : MonoBehaviour
{
    public Transform vrHeadTarget; // The head from Meta Quest
    public float followSpeed; // Smooth movement
    public float heightOffset; // Optional vertical offset to keep avatar grounded

    void LateUpdate()
    {
        if (vrHeadTarget == null) return;

        // Take headset position, but ignore head height
        Vector3 targetPosition = vrHeadTarget.position;
        targetPosition.y = heightOffset; // fix Y so avatar doesn't float

        // Smooth follow
        transform.position = Vector3.Lerp(transform.position, targetPosition, Time.deltaTime * followSpeed);
    }
}

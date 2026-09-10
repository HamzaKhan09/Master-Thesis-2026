using UnityEngine;

public class VRRootFollower : MonoBehaviour
{
    public Transform vrHeadTarget;
    public float followSpeed = 6f;

    [Tooltip("When true the avatar XZ follows the headset (needed for room-scale walking). Vertical height is owned by AvatarLegsIK foot-grounding.")]
    public bool followHeadHorizontal = true;

    [Tooltip("Pushes the body back from the headset along the avatar's facing, so the eyes sit at the avatar's face instead of inside its head — look down to see your own torso and legs. Try 0.1-0.3.")]
    public float bodyBackOffset = 0.15f;

    void LateUpdate()
    {
        if (vrHeadTarget == null) return;

        // Horizontal (XZ) follow only. Vertical position is driven by AvatarLegsIK foot-grounding
        // so crouching lowers the body while the feet stay planted on the floor.
        if (!followHeadHorizontal) return;

        Vector3 backShift = -transform.forward * bodyBackOffset;
        Vector3 targetPosition = transform.position;
        targetPosition.x = vrHeadTarget.position.x + backShift.x;
        targetPosition.z = vrHeadTarget.position.z + backShift.z;

        transform.position = Vector3.Lerp(transform.position, targetPosition, Time.deltaTime * followSpeed);
    }
}

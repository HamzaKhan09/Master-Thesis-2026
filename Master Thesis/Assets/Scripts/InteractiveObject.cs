using UnityEngine;

[RequireComponent(typeof(Rigidbody))]
public class InteractiveObject : MonoBehaviour
{
    [Header("Physics Settings")]
    public float kickForce = 15f;
    public float handForce = 8f;
    public bool canBeGrabbed = true;
    public float floorLevel = 0f;
    public float resetHeight = 0.5f;

    private Rigidbody rb;
    private Vector3 initialPosition;

    void Start()
    {
        rb = GetComponent<Rigidbody>();
        initialPosition = transform.position;
    }
void Update()
{
    if (Input.GetKeyDown(KeyCode.R))
    {
        InteractiveObject interactiveObject = FindFirstObjectByType<InteractiveObject>();
        if (interactiveObject != null)
        {
            interactiveObject.ResetPosition();
        }
    }
}
    void FixedUpdate()
    {
        if (transform.position.y < floorLevel)
        {
            ResetPosition();
        }
    }

    public void ApplyForce(Vector3 force)
    {
        if (rb != null)
        {
            rb.AddForce(force, ForceMode.Impulse);
        }
    }

    public void Grab(Transform grabParent)
    {
        if (!canBeGrabbed) return;
        
        if (rb != null)
        {
            rb.isKinematic = true;
            rb.linearVelocity = Vector3.zero;
            rb.angularVelocity = Vector3.zero;
        }
        
        transform.SetParent(grabParent);
        transform.localPosition = Vector3.zero;
    }

    public void Release(Vector3 throwVelocity)
    {
        transform.SetParent(null);
        
        if (rb != null)
        {
            rb.isKinematic = false;
            rb.AddForce(throwVelocity, ForceMode.VelocityChange);
        }
    }

    public void ResetPosition()
    {
        if (rb != null)
        {
            rb.linearVelocity = Vector3.zero;
            rb.angularVelocity = Vector3.zero;
        }
        transform.position = new Vector3(
            initialPosition.x,
            floorLevel + resetHeight,
            initialPosition.z
        );
    }
}

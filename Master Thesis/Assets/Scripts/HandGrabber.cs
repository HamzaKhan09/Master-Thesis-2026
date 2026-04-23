using UnityEngine;

public class HandGrabber : MonoBehaviour
{
    public enum HandSide { Left, Right }
    public HandSide handSide;
    
    [Header("Grab Settings")]
    public float grabRadius = 0.2f;
    public Transform grabPoint;
    public float throwForce = 8f;
    public OVRInput.Button grabButton = OVRInput.Button.PrimaryHandTrigger;

    [Header("Visual Feedback")]
    public Renderer handRenderer;
    public Color grabReadyColor = Color.yellow;
    public Color grabbingColor = Color.green;
    private Color originalColor;

    private GameObject grabbedObject;
    private bool canGrab;

    void Start()
    {
        if (grabPoint == null) grabPoint = transform;
        if (handRenderer) originalColor = handRenderer.material.color;
    }

    void Update()
    {
        CheckGrabInput();
        UpdateGrabbedObject();
        UpdateHandVisuals();
    }

    void CheckGrabInput()
    {
        OVRInput.Controller controller = (handSide == HandSide.Left) ? 
            OVRInput.Controller.LTouch : OVRInput.Controller.RTouch;
        
        bool grabInput = OVRInput.GetDown(grabButton, controller);
        
        if (grabInput)
        {
            if (canGrab && grabbedObject == null)
            {
                GrabObject();
            }
            else if (grabbedObject != null)
            {
                ReleaseObject();
            }
        }
    }

    void GrabObject()
    {
        Collider[] colliders = Physics.OverlapSphere(grabPoint.position, grabRadius);
        foreach (Collider col in colliders)
        {
            if (col.CompareTag("Interactable") && col.TryGetComponent<InteractiveObject>(out var interactiveObj))
            {
                grabbedObject = col.gameObject;
                interactiveObj.Grab(grabPoint);
                break;
            }
        }
    }

    void ReleaseObject()
    {
        if (grabbedObject == null) return;
        
        if (grabbedObject.TryGetComponent<InteractiveObject>(out var interactiveObj))
        {
            Vector3 throwVelocity = grabPoint.forward * throwForce;
            interactiveObj.Release(throwVelocity);
        }
        grabbedObject = null;
    }

    void UpdateGrabbedObject()
    {
        if (grabbedObject && grabbedObject.transform.parent != grabPoint)
        {
            grabbedObject.transform.position = Vector3.Lerp(
                grabbedObject.transform.position,
                grabPoint.position,
                Time.deltaTime * 20f
            );
        }
    }

    void UpdateHandVisuals()
    {
        if (!handRenderer) return;
        
        handRenderer.material.color = grabbedObject ? 
            grabbingColor : 
            (canGrab ? grabReadyColor : originalColor);
    }

    void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("Interactable")) canGrab = true;
    }

    void OnTriggerExit(Collider other)
    {
        if (other.CompareTag("Interactable")) canGrab = false;
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = canGrab ? Color.green : Color.yellow;
        Gizmos.DrawWireSphere(grabPoint.position, grabRadius);
    }
}
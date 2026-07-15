using UnityEngine;

public class LimbCollider : MonoBehaviour
{
    [Header("Kick Settings")]
    public float pushForce = 10f;
    public float interactionRadius = 0.15f;
    public bool isFoot = true;

    private SphereCollider sphereCollider;

    void Start()
    {
        sphereCollider = gameObject.AddComponent<SphereCollider>();
        sphereCollider.radius = interactionRadius;
        sphereCollider.isTrigger = true;
    }

    void OnTriggerEnter(Collider other)
    {
        if (isFoot && other.TryGetComponent<InteractiveObject>(out var interactiveObj))
        {
            Vector3 direction = (other.transform.position - transform.position).normalized;
            interactiveObj.ApplyForce(direction * pushForce);
        }
    }
}

using UnityEngine;

public class GoalLine : MonoBehaviour
{
    public string ballTag = "Ball";
    public AudioClip victorySound;
    public float cooldown = 3f;

    private AudioSource audioSource;
    private float nextGoalTime;

    void Start()
    {
        audioSource = gameObject.AddComponent<AudioSource>();
        audioSource.playOnAwake = false;
        audioSource.spatialBlend = 0f;
    }

    void OnTriggerEnter(Collider other)
    {
        if (!other.CompareTag(ballTag)) return;
        if (Time.time < nextGoalTime) return;

        nextGoalTime = Time.time + cooldown;
        Debug.Log("GOAL!");

        if (victorySound != null)
            audioSource.PlayOneShot(victorySound);
    }
}

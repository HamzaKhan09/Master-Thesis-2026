using UnityEngine;

/// <summary>
/// Keeps the ball out of play until B is pressed. R remains owned by
/// InteractiveObject, which resets the ball to this scene's configured spawn point.
/// </summary>
public class BallSpawner : MonoBehaviour
{
    [SerializeField] private GameObject ball;
    [SerializeField] private KeyCode spawnKey = KeyCode.B;

    private void Update()
    {
        if (ball != null && Input.GetKeyDown(spawnKey) && !ball.activeSelf)
        {
            ball.SetActive(true);
        }
    }
}

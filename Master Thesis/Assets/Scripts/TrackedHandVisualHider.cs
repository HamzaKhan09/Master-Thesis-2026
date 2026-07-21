using UnityEngine;

// Meta's tracked-hand visual re-enables its own renderer every Update() (_updateVisibility),
// undoing a one-shot hide. Re-hide after all Updates run so the tracked hand mesh ("shadow
// hands") never flashes back on over the OptiTrack-driven avatar hands.
//
// The OpenXR hand-tracking anchors aren't guaranteed to exist yet when Start() runs (OVR
// spins them up asynchronously), so the lookup retries every frame until it resolves instead
// of a one-shot Start()-time Find that can silently come back empty.
public class TrackedHandVisualHider : MonoBehaviour
{
    public Transform leftHandVisualRoot;
    public Transform rightHandVisualRoot;

    void LateUpdate()
    {
        if (leftHandVisualRoot == null)
        {
            // Confirmed by disabling each candidate in Play mode: the visible mesh isn't
            // under OpenXR*Hand (joint skeleton only) or OVR*HandVisual — it's somewhere in
            // this whole building block, likely the legacy OculusHand_L/R sibling branch.
            // Hide from here so both the OpenXR and legacy paths are covered regardless.
            GameObject leftHand = GameObject.Find("[BuildingBlock] Synthetic Left Hand");
            leftHandVisualRoot = leftHand != null ? leftHand.transform : null;
        }

        if (rightHandVisualRoot == null)
        {
            GameObject rightHand = GameObject.Find("[BuildingBlock] Synthetic Right Hand");
            rightHandVisualRoot = rightHand != null ? rightHand.transform : null;
        }

        Hide();
    }

    private void Hide()
    {
        HideRenderers(leftHandVisualRoot);
        HideRenderers(rightHandVisualRoot);
    }

    private void HideRenderers(Transform root)
    {
        if (root == null)
        {
            return;
        }

        foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
        {
            renderer.enabled = false;
        }
    }
}

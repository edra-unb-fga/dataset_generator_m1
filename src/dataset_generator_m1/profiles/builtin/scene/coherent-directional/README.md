# Coherent scene with directional shade

Experimental review-only variant pairing the refined scene's local background
adaptation and elliptical shade with a sampled directional slab. It is intended
for use with `builtin:appearance/coherent-refined`. Shade affects foreground and
background through the shared homography; it is a qualitative approximation, not
calibrated lighting, a caster or contact shadow. The slab can miss the target, and
its straight edges can look procedural. This profile does not change any default.

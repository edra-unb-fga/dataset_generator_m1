# Scaled capture closing review

The opt-in scaled nominees use a 640px reference and shorter-side scaling for
`WeightedMotionBlur`; existing fixed-pixel profiles remain unchanged. This is an
engineering policy, not calibrated physical camera motion.

The guarded study generated 96 images: eight cases for each of landing-pad,
landing and manometro, fixed/scaled pairs at 640 and 1280. Each family included
two forced severe, two forced moderate, one forced mild, one disabled and two
naturally sampled motion cases. Background groups, target-size strata and shade
activation were deliberately selected, so these cells are not estimates of
natural effect frequency. Within each resolution all fixed/scaled pairs matched
geometry, mask signatures, background source hashes and sampled parameters;
all 640px image hashes also matched. Review full images and target crops.

The original run's cross-resolution verifier used the wrong foreground coordinate
convention and recorded `review-needed`/failed; both original outputs are retained.
The corrected separate recheck compares foreground transforms in resized-raster
coordinates. It passes 23 of 24 scene cases. Landing case 0 remains review-needed:
instance-001's visible bbox fraction was 0.708725 at 640 (accepted) and 0.699553
at 1280 (rejected against the 0.70 threshold). This is a real threshold-sensitive
annotation difference, not silently treated as equivalence. Within-resolution
pairs continue to match. Do not extrapolate the small screen to all sizes.

The run's driver snapshot SHA-256 is
`6809c0a1a8c40aaa9697bc6f199d37f66460e10a2077aba311c46cae787361e7`;
the later corrected verifier's fingerprint is recorded in
`cross-resolution-recheck.json`. The tracked driver has since changed to correct
that verifier and improve report metadata. A run using it is new evidence, not
identical historical provenance. The run recorded a host-wide swap-out warning;
independent host and RSS guards remained active.

The 3D review reuses 24 balanced-mixture and 12 broad-material natural renders,
and 18 selected matched component-lighting renders. The mixture samples are
unmatched, reuse assets and do not measure clipping or shadow prevalence. No new
3D runtime was allocated. The final user review is separate for each 2D family
and for 3D; unapproved candidates are not promoted.

Raw images, driver snapshots and artifacts remain under ignored
`outputs/experiments/scaled-review-full-20261106/`; the local 2D and 3D galleries
and checksum-verified portable review bundles remain separately retained. See
`experiments/foreground-context/coherent-study/scaled_review.py` for the study
invocation and `scripts/package_review_gallery.py` for bundle verification.

# Decision 003: Accepted-output completion is the primary ETA

Preflight estimates completion from accepted-output throughput and observed rejection behavior.
Candidate/render cost remains a secondary diagnostic because it does not describe how long a user must
wait for the requested number of accepted samples.

Exact-worker local observations have the strongest local confidence. Cross-worker and low-sample
observations widen the reported range; no machine-independent latency threshold follows from them.

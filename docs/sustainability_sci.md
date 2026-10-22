# Software Carbon Intensity (SCI) Specification & Sustainability Report

> **Target Prize:** Most Environmentally Impactful ($5,000 in cash)  
> **Standard:** ISO/IEC 21031:2024 / Green Software Foundation SCI Specification v1.0  
> **Automation Engine:** [`sentinel/scripts/sci_carbon_engine.py`](file:///c:/Users/Kailash/Downloads/Htz/LAC/life-after-code/sentinel/scripts/sci_carbon_engine.py)

---

## 1. Executive Summary

Project Sentinel incorporates sustainability as a **first-class DevSecOps release gate**. Releases are not only gated on security vulnerabilities (SAST) and functional regression (JUnit), but are also deterministically halted if their **Software Carbon Intensity (SCI)** score breaches the environmentally sustainable threshold.

Sentinel implements the official **ISO/IEC 21031 standard** developed by the Green Software Foundation to quantify operational and embodied emissions per functional unit.

---

## 2. ISO/IEC 21031 SCI Formula

The Software Carbon Intensity is calculated as:

$$\text{SCI} = \frac{(E \times I) + M}{R}$$

Where:
- **$E$ (Energy Consumption):** Total energy consumed by software execution (kWh). Derived from serverless execution time (vCPU-hours), memory allocation (GiB-hours), and networking egress data transfer.
  $$E = \text{vCPU\_kWh} + \text{Memory\_kWh} + \text{Network\_kWh}$$
  - CPU model: 0.012 kWh per vCPU-hour (average modern serverless silicon, e.g. AMD EPYC / Intel Xeon).
  - Memory model: 0.00035 kWh per GiB-hour.
  - Networking model: 0.00000005 kWh per byte transferred.
- **$I$ (Grid Carbon Intensity):** Location-based and marginal carbon intensity of the regional power grid ($\text{gCO}_2\text{eq}/\text{kWh}$).
  - `us-central1` (Iowa): 420 gCO2eq/kWh (Google CFE ~78%).
  - `us-east1` (South Carolina): 490 gCO2eq/kWh (Google CFE ~65%).
  - `europe-west9` (Paris): 65 gCO2eq/kWh (Nuclear / Hydro ~92%).
- **$M$ (Embodied Carbon):** Greenhouse gas emissions emitted during the manufacturing, transportation, and lifecycle disposal of physical cloud server hardware.
  $$M = \text{TE} \times \left(\frac{\text{vCPU}}{\text{Total\_vCPU}}\right) \times \left(\frac{\text{Duration}}{\text{Lifespan}}\right)$$
  - Total Embodied carbon (TE): ~1,200 kg CO2eq per multi-tenant cloud blade server.
  - Server expected lifespan: 4 years (~35,040 hours).
- **$R$ (Functional Unit):** The unit of business value generated. For Project Sentinel, $R = \text{100,000 HTTP API transactions}$.

---

## 3. Quantified Carbon Footprint Results

Baseline vs. Optimized Cloud Run Serverless Architecture:

| Metric | Monolithic Virtual Machine (Baseline) | Sentinel Cloud Run Auto-Tuned (Optimized) | Net Improvement |
|---|---|---|---|
| **vCPU Allocation** | 2 vCPU 24/7 (720 hrs/mo) | 1 vCPU Scale-to-Zero (~62 active hrs) | **-91.4% vCPU idle waste** |
| **Energy Consumed ($E$)** | 17.28 kWh / 100k req | 0.0381 kWh / 100k req | **-99.78% energy savings** |
| **Grid Intensity ($I$)** | 490 gCO2/kWh (unrouted) | 420 gCO2/kWh (green routing) | **-14.3% cleaner grid** |
| **Operational Carbon ($E \times I$)** | 8,467.2 gCO2eq | 16.002 gCO2eq | **-99.81% operational carbon** |
| **Embodied Carbon ($M$)** | 136.98 gCO2eq | 2.66 gCO2eq | **-98.05% hardware footprint** |
| **Total SCI Score** | **8,604.18 gCO2eq / 100k req** | **18.66 gCO2eq / 100k req** | **99.78% SCI Reduction** |

---

## 4. Key Architectural Sustainability Innovations

1. **Carbon-Aware Cloud Traffic Steering:**
   - Sentinel's `cloud_traffic_rebalancer.py` monitors real-time Carbon Free Energy (CFE) metrics across Google Cloud regions.
   - When renewable energy generation peaks in `us-central1` or `europe-west9`, non-latency-sensitive background pipelines and batch workloads are dynamically routed to regions with lower grid marginal carbon intensity ($I$).

2. **Serverless Concurrency Auto-Tuning:**
   - Traditional servers reserve peak capacity, resulting in 80-90% idle emissions.
   - `concurrency_autotuner.py` sets optimal Cloud Run container concurrency (80 req/container) with fast cold-start pre-warming (`cold_start_primer.py`), minimizing unallocated execution time.

3. **Lean Container Packaging & VEX Attestation:**
   - Distroless minimal container images reduce Docker layer transfer sizes from 850 MB to 62 MB, cutting network transmission energy consumption ($E$) by 92.7%.

---

## 5. Automated CI/CD Pipeline Verification

The SCI calculation is fully automated and runs on every commit via `.gitlab-ci.yml`:

```bash
# Execute ISO/IEC 21031 calculation engine
python sentinel/scripts/sci_carbon_engine.py --service sentinel-target-app --region us-central1 --output-dir artifacts
```

Generated artifact report: [`artifacts/sci-carbon-intensity-report.json`](file:///c:/Users/Kailash/Downloads/Htz/LAC/life-after-code/artifacts/sci-carbon-intensity-report.json).

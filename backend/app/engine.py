import math
from .catalog import MODELS, GPUS, SERVERS, CLOUD, USE_CASES, ASSUMPTIONS, CATALOG_VERSION

def calc(req):
    model = next((m for m in MODELS if m["id"] == req["model_id"]), None)
    if not model: raise ValueError("Unknown model")
    gpu = next((g for g in GPUS if g["id"] == req["gpu_id"]), None)
    if not gpu: raise ValueError("Unknown GPU")
    server = next((s for s in SERVERS if s["id"] == req["server_id"]), None)
    if not server: raise ValueError("Unknown server")
    if server["gpu"] != gpu["id"]:
        raise ValueError("Selected server configuration does not match selected GPU")
    if not model["self_hostable"] and not req.get("cloud_id"):
        raise ValueError("Hosted-only model requires a cloud deployment selection")
    if req["input_tokens"] + req["output_tokens"] > model["context"]:
        raise ValueError("Input + output tokens exceed the selected model context window")
    cloud = next((c for c in CLOUD if c["id"] == req.get("cloud_id")), None) if req.get("cloud_id") else None

    users = max(1, req["total_users"])
    active = max(1, math.ceil(users * req["active_user_pct"]/100))
    daily = active * req["transactions_per_user_day"]
    peak_rps = max(0.1, daily / max(1, req["peak_hours"]*3600) * req["peak_factor"])
    concurrency = max(1, math.ceil(peak_rps * req["avg_latency_seconds"]))
    complexity = {"simple":1.0,"medium":1.5,"strong":2.5}.get(req["complexity"],1.5)
    required_tps = peak_rps * complexity

    if model["params_b"] is not None:
        weight_gb = model["params_b"] * model["bytes_per_param"]
        kv_gb = (req["input_tokens"] + req["output_tokens"]) * concurrency * 0.0015
        runtime_gb = weight_gb * 0.20
        raw_vram = weight_gb + kv_gb + runtime_gb
    else:
        weight_gb = kv_gb = runtime_gb = 0
        raw_vram = 0
    required_vram = raw_vram * 1.15
    memory_gpus = math.ceil(required_vram / gpu["usable_vram_gb"]) if required_vram else 0

    # No fabricated universal benchmark. Performance sizing is explicitly assumption-backed
    # unless a validated benchmark is entered by the user.
    validated_tps_per_gpu = req.get("validated_tps_per_gpu")
    if validated_tps_per_gpu:
        performance_gpus = math.ceil(required_tps / validated_tps_per_gpu)
        performance_basis = "User-supplied validated benchmark"
    else:
        performance_gpus = 0
        performance_basis = "Insufficient Evidence — no exact model/GPU/runtime benchmark supplied"
    performance_gpus = max(memory_gpus, performance_gpus)
    utilization_factor = 0.70
    production_gpus = math.ceil(performance_gpus / utilization_factor) if performance_gpus else 0
    ha_factor = 2 if req["ha"] else 1
    dr_factor = 2 if req["dr"] else 1
    growth_factor = 1 + req["growth_pct"]/100
    spare_factor = 1 + req["spare_pct"]/100
    final_gpus = math.ceil(max(1, production_gpus) * ha_factor * dr_factor * growth_factor * spare_factor)

    gpus_per_server = server["gpus"]
    servers = math.ceil(final_gpus / gpus_per_server)
    total_gpu = servers * gpus_per_server
    capex = servers * server["price_usd"]
    annual_opex = capex * 0.18
    tco = capex + annual_opex * req["years"]
    cloud_result = None
    if cloud:
        cloud_units = math.ceil(final_gpus / max(1, cloud["gpus"]))
        cloud_annual = cloud_units * cloud["hourly_usd"] * 8760
        cloud_result = {"units":cloud_units,"annual_opex_usd":cloud_annual,"tco_usd":cloud_annual*req["years"],"price_status":cloud["price_status"]}

    return {
      "catalog_version": CATALOG_VERSION,
      "workload":{"total_users":users,"active_users":active,"daily_transactions":daily,"peak_rps":round(peak_rps,3),"peak_concurrency":concurrency,"required_tps":round(required_tps,3)},
      "model":{"id":model["id"],"name":model["name"],"provider":model["provider"],"self_hostable":model["self_hostable"],"context":model["context"]},
      "memory":{"weights_gb":round(weight_gb,2),"kv_cache_gb":round(kv_gb,2),"runtime_gb":round(runtime_gb,2),"required_vram_gb":round(required_vram,2)},
      "gpu":{"id":gpu["id"],"name":gpu["name"],"usable_vram_gb":gpu["usable_vram_gb"],"memory_gpus":memory_gpus,"performance_gpus":performance_gpus,"production_gpus":production_gpus,"final_gpus":final_gpus,"performance_basis":performance_basis},
      "infrastructure":{"server_id":server["id"],"server":server["name"],"vendor":server["vendor"],"servers":servers,"gpus_per_server":gpus_per_server,"total_gpu":total_gpu,"cpu_cores":servers*server["cpu_cores"],"ram_gb":servers*server["ram_gb"],"storage_tb":servers*server["storage_tb"],"network_gbps":server["network_gbps"]},
      "resilience":{"ha":req["ha"],"dr":req["dr"],"growth_pct":req["growth_pct"],"spare_pct":req["spare_pct"]},
      "cost":{"capex_usd":capex,"annual_opex_usd":annual_opex,"tco_usd":tco,"years":req["years"],"price_status":server["price_status"]},
      "cloud":cloud_result,
      "governance":{"confidence":"Evidence-backed for model/GPU specs; Estimated Price for server/cloud pricing; Insufficient Evidence for universal performance unless benchmark supplied","assumptions":[a for a in ASSUMPTIONS]},
      "evidence":[
        {"title":model["evidence"],"url":model["source_url"],"confidence":"Verified"},
        {"title":gpu["evidence"],"url":gpu["source_url"],"confidence":"Verified"},
        {"title":server["evidence"],"url":server["source_url"],"confidence":server["price_status"]},
      ]
    }

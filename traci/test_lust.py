from pathlib import Path
import traci

# Racine du projet
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Scénario LuST Luxembourg
SUMO_CONFIG = PROJECT_ROOT / "LuSTScenario" / "scenario" / "dua.actuated.sumocfg"

sumo_cmd = [
    "sumo",
    "-c",
    str(SUMO_CONFIG)
]

print("======================================")
print("  TRA CI - LUXEMBOURG LuST TEST")
print("======================================")
print("Démarrage de SUMO...")
print(f"Configuration : {SUMO_CONFIG}")

traci.start(sumo_cmd)

print("Connexion TraCI réussie !")
print()

for step in range(100):
    traci.simulationStep()

    vehicles = traci.vehicle.getIDList()

    print(
        f"Step {step:03d} | "
        f"Véhicules présents : {len(vehicles)}"
    )

traci.close()

print()
print("Simulation terminée.")
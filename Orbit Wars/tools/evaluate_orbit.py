import argparse
import csv
import json
import statistics
from pathlib import Path

from kaggle_environments import make


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Orbit Wars agents over many seeds.")
    parser.add_argument("--agent", default="main.py", help="Agent file to test as player 0.")
    parser.add_argument("--opponent", default="agents/stable_540.py", help="Opponent agent file or built-in.")
    parser.add_argument("--games", type=int, default=25, help="Number of seeds to run.")
    parser.add_argument("--seed", type=int, default=1000, help="Starting seed.")
    parser.add_argument("--players", type=int, choices=(2, 4), default=2)
    parser.add_argument("--out", default="eval_results.csv", help="CSV output path.")
    parser.add_argument("--save-replays", action="store_true", help="Write replay JSONs for losses.")
    return parser.parse_args()


def player_total(final_state, player):
    obs = final_state[player].observation
    planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    fleets = obs.get("fleets", []) if isinstance(obs, dict) else obs.fleets
    planet_ships = sum(int(p[5]) for p in planets if int(p[1]) == player)
    fleet_ships = sum(int(f[6]) for f in fleets if int(f[1]) == player)
    production = sum(int(p[6]) for p in planets if int(p[1]) == player)
    planet_count = sum(1 for p in planets if int(p[1]) == player)
    return planet_count, production, planet_ships + fleet_ships


def run_game(agent, opponent, players, seed, save_replays):
    agents = [agent] + [opponent] * (players - 1)
    env = make("orbit_wars", configuration={"seed": seed}, debug=True)
    env.run(agents)
    final = env.steps[-1]
    rewards = [state.reward for state in final]
    statuses = [state.status for state in final]
    best_reward = max(rewards)
    won = rewards[0] == best_reward and rewards.count(best_reward) == 1
    tied = rewards.count(best_reward) > 1 and rewards[0] == best_reward
    totals = [player_total(final, player) for player in range(players)]

    if save_replays and not won:
        replay_dir = Path("eval_replays")
        replay_dir.mkdir(exist_ok=True)
        replay_path = replay_dir / f"seed_{seed}_loss.json"
        replay_path.write_text(json.dumps(env.toJSON(), separators=(",", ":")), encoding="utf-8")

    return {
        "seed": seed,
        "won": int(won),
        "tied": int(tied),
        "reward0": rewards[0],
        "rewards": json.dumps(rewards),
        "statuses": json.dumps(statuses),
        "p0_planets": totals[0][0],
        "p0_prod": totals[0][1],
        "p0_ships": totals[0][2],
        "opp_best_prod": max(t[1] for t in totals[1:]),
        "opp_best_ships": max(t[2] for t in totals[1:]),
    }


def main():
    args = parse_args()
    rows = []
    for offset in range(args.games):
        seed = args.seed + offset
        row = run_game(args.agent, args.opponent, args.players, seed, args.save_replays)
        rows.append(row)
        print(
            f"seed={seed} won={row['won']} tied={row['tied']} "
            f"p0_prod={row['p0_prod']} p0_ships={row['p0_ships']} rewards={row['rewards']}"
        )

    fieldnames = list(rows[0].keys()) if rows else []
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    wins = sum(row["won"] for row in rows)
    ties = sum(row["tied"] for row in rows)
    prod_margin = [row["p0_prod"] - row["opp_best_prod"] for row in rows]
    ship_margin = [row["p0_ships"] - row["opp_best_ships"] for row in rows]
    print()
    print(f"wins={wins}/{len(rows)} ties={ties}/{len(rows)}")
    print(f"avg_prod_margin={statistics.mean(prod_margin):.2f}")
    print(f"avg_ship_margin={statistics.mean(ship_margin):.2f}")
    print(f"wrote={args.out}")


if __name__ == "__main__":
    main()

import argparse

from kaggle_environments import make


def main():
    parser = argparse.ArgumentParser(description="Run local Orbit Wars matches.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--players", type=int, choices=(2, 4), default=2)
    parser.add_argument("--opponent", default="random")
    args = parser.parse_args()

    agents = ["main.py"] + [args.opponent] * (args.players - 1)
    wins = 0

    for offset in range(args.games):
        seed = args.seed + offset
        env = make("orbit_wars", configuration={"seed": seed}, debug=True)
        env.run(agents)
        final = env.steps[-1]
        rewards = [state.reward for state in final]
        statuses = [state.status for state in final]
        best_reward = max(rewards)
        won = rewards[0] == best_reward and rewards.count(best_reward) == 1
        wins += int(won)
        print(f"seed={seed} rewards={rewards} statuses={statuses} won={won}")

    print(f"wins={wins}/{args.games}")


if __name__ == "__main__":
    main()

import math


CENTER_X = 50.0
CENTER_Y = 50.0
BOARD_SIZE = 100.0
SUN_RADIUS = 10.0
ROTATION_RADIUS_LIMIT = 50.0
MAX_SHIP_SPEED = 6.0
INFERRED_STEP = -1


def orbit_wars_agent(obs):
    player = get_field(obs, "player", 0)
    step = get_step(obs)
    planets = [planet_from_raw(raw) for raw in get_field(obs, "planets", [])]
    fleets = [fleet_from_raw(raw) for raw in get_field(obs, "fleets", [])]
    initial_planets = {
        int(raw[0]): planet_from_raw(raw)
        for raw in get_field(obs, "initial_planets", [])
        if len(raw) >= 7
    }
    comet_ids = set(get_field(obs, "comet_planet_ids", []))
    angular_velocity = float(get_field(obs, "angular_velocity", 0.0))
    comets = get_field(obs, "comets", [])

    my_planets = [p for p in planets if p["owner"] == player]
    if not my_planets:
        return []

    my_production = sum(p["production"] for p in planets if p["owner"] == player)
    enemy_production = max(
        [sum(p["production"] for p in planets if p["owner"] == owner) for owner in range(4) if owner != player],
        default=0,
    )
    behind_on_production = step > 80 and my_production + 5 < enemy_production
    incoming = estimate_incoming_enemy_fleets(my_planets, fleets, player)
    moves = []
    reserved = {}

    for source in sorted(my_planets, key=lambda p: -p["production"]):
        reserve = reserve_for(source, incoming.get(source["id"], 0), step, len(my_planets))
        if behind_on_production:
            reserve = min(reserve, max(4, source["production"] * 2 + 4))
        reserved[source["id"]] = min(source["ships"], reserve)

    reinforce_moves = build_reinforcements(my_planets, incoming, reserved)
    planet_by_id = {p["id"]: p for p in my_planets}
    for move in reinforce_moves:
        source_planet = planet_by_id.get(move[0])
        if source_planet is None or move[2] >= min_launch_size(source_planet, step, len(my_planets)):
            moves.append(move)

    targets = [p for p in planets if p["owner"] != player]
    planned_target_pressure = {}

    if step >= 45 or len(my_planets) >= 4:
        wave_moves = build_greedy_waves(
            my_planets,
            targets,
            planets,
            player,
            reserved,
            planned_target_pressure,
            fleets,
            initial_planets,
            angular_velocity,
            comet_ids,
            comets,
            step,
        )
        if wave_moves:
            moves.extend(wave_moves)
            return moves[:20]

    for source in sorted(my_planets, key=lambda p: available_ships(p, reserved), reverse=True):
        source_available = available_ships(source, reserved)
        min_launch = min_launch_size(source, step, len(my_planets))
        if source_available < min_launch:
            continue

        choice = choose_opening_target(
            source,
            targets,
            source_available,
            initial_planets,
            angular_velocity,
            comet_ids,
            comets,
            step,
            len(my_planets),
        )
        if choice is None:
            choice = choose_target(
                source,
                targets,
                planets,
                player,
                source_available,
                planned_target_pressure,
                fleets,
                initial_planets,
                angular_velocity,
                comet_ids,
                comets,
                step,
            )
        if choice is None:
            continue

        target, angle, ships = choice
        ships = min(ships, source_available)
        if ships < min_launch:
            continue

        moves.append([source["id"], angle, ships])
        reserved[source["id"]] += ships
        planned_target_pressure[target["id"]] = planned_target_pressure.get(target["id"], 0) + ships

    return moves[:20]


def get_field(obs, name, default):
    if isinstance(obs, dict):
        return obs.get(name, default)
    return getattr(obs, name, default)


def get_step(obs):
    global INFERRED_STEP
    explicit_step = get_field(obs, "step", None)
    if explicit_step is not None:
        INFERRED_STEP = int(explicit_step)
        return INFERRED_STEP
    explicit_turn = get_field(obs, "turn", None)
    if explicit_turn is not None:
        INFERRED_STEP = int(explicit_turn)
        return INFERRED_STEP
    INFERRED_STEP += 1
    return INFERRED_STEP


def planet_from_raw(raw):
    return {
        "id": int(raw[0]),
        "owner": int(raw[1]),
        "x": float(raw[2]),
        "y": float(raw[3]),
        "radius": float(raw[4]),
        "ships": int(raw[5]),
        "production": int(raw[6]),
    }


def fleet_from_raw(raw):
    return {
        "id": int(raw[0]),
        "owner": int(raw[1]),
        "x": float(raw[2]),
        "y": float(raw[3]),
        "angle": float(raw[4]),
        "from_planet_id": int(raw[5]),
        "ships": int(raw[6]),
    }


def reserve_for(planet, incoming_enemy, step, owned_planet_count):
    if step < 80 and owned_planet_count <= 2:
        return int(max(3, incoming_enemy + 1))
    base = 8 + planet["production"] * 4
    if step > 100:
        base += planet["production"] * 4
    if step > 330:
        base = 3 + planet["production"] * 2
    return int(max(base, incoming_enemy + planet["production"] * 2 + 6))


def available_ships(planet, reserved):
    return max(0, planet["ships"] - reserved.get(planet["id"], 0))


def min_launch_size(planet, step, owned_planet_count):
    if step < 80 and owned_planet_count <= 3:
        return 5
    if step >= 100:
        return max(10, planet["production"] * 3)
    if step < 220:
        return max(8, planet["production"] * 3)
    return max(14, planet["production"] * 4)


def estimate_incoming_enemy_fleets(my_planets, fleets, player):
    incoming = {p["id"]: 0 for p in my_planets}
    for fleet in fleets:
        if fleet["owner"] == player:
            continue
        for planet in my_planets:
            if is_fleet_heading_to_planet(fleet, planet):
                incoming[planet["id"]] += fleet["ships"]
                break
    return incoming


def is_fleet_heading_to_planet(fleet, planet):
    dx = math.cos(fleet["angle"])
    dy = math.sin(fleet["angle"])
    px = planet["x"] - fleet["x"]
    py = planet["y"] - fleet["y"]
    along = px * dx + py * dy
    if along <= 0:
        return False
    closest_x = fleet["x"] + dx * along
    closest_y = fleet["y"] + dy * along
    return distance_xy(closest_x, closest_y, planet["x"], planet["y"]) <= planet["radius"] + 0.8


def build_reinforcements(my_planets, incoming, reserved):
    moves = []
    threatened = [
        p for p in my_planets
        if incoming.get(p["id"], 0) > p["ships"] - reserved.get(p["id"], 0)
    ]
    donors = sorted(my_planets, key=lambda p: available_ships(p, reserved), reverse=True)

    for target in threatened:
        need = incoming[target["id"]] + 3 - max(0, target["ships"] - reserved.get(target["id"], 0))
        for donor in donors:
            if need <= 0:
                break
            if donor["id"] == target["id"]:
                continue
            available = available_ships(donor, reserved)
            if available < 10:
                continue
            ships = min(available // 2, need)
            if ships < 6:
                continue
            moves.append([donor["id"], angle_between(donor, target), int(ships)])
            reserved[donor["id"]] += int(ships)
            need -= int(ships)
    return moves


def build_greedy_waves(
    my_planets,
    targets,
    planets,
    player,
    reserved,
    planned_pressure,
    fleets,
    initial_planets,
    angular_velocity,
    comet_ids,
    comets,
    step,
):
    budgets = {
        source["id"]: available_ships(source, reserved)
        for source in my_planets
    }
    source_by_id = {source["id"]: source for source in my_planets}
    target_pressure = dict(planned_pressure)
    moves = []
    used_targets = set()
    max_waves = 8 if step < 170 else 10

    for _ in range(max_waves):
        best = None
        for source in sorted(my_planets, key=lambda p: budgets.get(p["id"], 0), reverse=True)[:12]:
            available = budgets.get(source["id"], 0)
            if available < min_launch_size(source, step, len(my_planets)):
                continue
            for target in shortlisted_targets(source, targets, player, comet_ids, step):
                candidate = score_wave_candidate(
                    source,
                    target,
                    planets,
                    player,
                    available,
                    target_pressure,
                    fleets,
                    initial_planets,
                    angular_velocity,
                    comet_ids,
                    comets,
                    step,
                )
                if candidate is None:
                    continue
                if candidate[2] in used_targets:
                    continue
                if best is None or candidate[0] > best[0]:
                    best = candidate

        if best is None:
            break

        score, source_id, target_id, angle, ships = best
        if score < greedy_wave_threshold(step):
            break
        source = source_by_id.get(source_id)
        if source is None:
            break
        ships = min(int(ships), budgets.get(source_id, 0))
        if ships < min_launch_size(source, step, len(my_planets)):
            break
        moves.append([source_id, angle, ships])
        used_targets.add(target_id)
        budgets[source_id] -= ships
        reserved[source_id] = reserved.get(source_id, 0) + ships
        target_pressure[target_id] = target_pressure.get(target_id, 0) + ships

    if moves:
        add_regroup_moves(my_planets, planets, player, budgets, moves, step)
    return moves


def shortlisted_targets(source, targets, player, comet_ids, step):
    scored = []
    for target in targets:
        if target["id"] in comet_ids and step > 420:
            continue
        if target["owner"] == -1:
            priority = target["production"] * 80.0 - target["ships"] * 2.7
            if step > 160 and target["production"] <= 1:
                priority -= 80.0
        else:
            priority = target["production"] * (120.0 if step > 90 else 80.0) + target["ships"] * 0.08
        priority -= distance(source, target) * (1.4 if step < 130 else 0.9)
        scored.append((priority, target))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [target for _, target in scored[:14]]


def score_wave_candidate(
    source,
    target,
    planets,
    player,
    available,
    target_pressure,
    fleets,
    initial_planets,
    angular_velocity,
    comet_ids,
    comets,
    step,
):
    pressure = target_pressure.get(target["id"], 0)
    rough_aim_x, rough_aim_y = predict_position(
        target,
        max(1, min(available, target["ships"] + 1)),
        source,
        initial_planets,
        angular_velocity,
        comet_ids,
        comets,
    )
    rough_travel = distance_xy(source["x"], source["y"], rough_aim_x, rough_aim_y)
    needed = ships_needed_for_target(target, player, pressure, fleets, rough_travel, available)
    needed = attack_packet_size(target, needed, available, comet_ids, step)
    if needed > available:
        return None

    send = greedy_wave_size(target, needed, available, step)
    if send > available:
        return None

    aim_x, aim_y = predict_position(target, send, source, initial_planets, angular_velocity, comet_ids, comets)
    if crosses_sun(source["x"], source["y"], aim_x, aim_y):
        return None
    if blocked_by_planet(source, target, aim_x, aim_y, planets):
        return None

    travel = distance_xy(source["x"], source["y"], aim_x, aim_y)
    eta = max(1.0, travel / ship_speed(send))
    angle = math.atan2(aim_y - source["y"], aim_x - source["x"])
    value = target_score(target, source, player, needed, eta, comet_ids, step)
    if target["owner"] not in (-1, player):
        value += enemy_pressure_bonus(target, step)
    if target["owner"] == -1 and step > 180 and target["production"] <= 1:
        value -= 120.0
    score = (value / max(1.0, send)) + math.sqrt(max(1, send)) * 0.16
    return score, source["id"], target["id"], angle, int(send)


def greedy_wave_size(target, needed, available, step):
    if target["owner"] == -1:
        if step < 80:
            return needed
        if target["production"] >= 4 and available >= needed + 12:
            return min(available, max(needed, int(available * 0.45)))
        return needed

    if step < 90:
        return needed
    if available >= 90:
        return min(available, max(needed, int(available * 0.62)))
    if available >= needed + 20:
        return min(available, needed + max(8, target["production"] * 4))
    return needed


def greedy_wave_threshold(step):
    if step < 80:
        return 2.1
    if step < 180:
        return 1.4
    if step < 330:
        return 0.9
    return 0.25


def enemy_pressure_bonus(target, step):
    bonus = 55.0 + target["production"] * (35.0 if step < 180 else 55.0)
    if target["ships"] > 100:
        bonus += min(80.0, target["ships"] * 0.12)
    return bonus


def add_regroup_moves(my_planets, planets, player, budgets, moves, step):
    if step < 70 or len(my_planets) < 5:
        return
    owned = sorted(my_planets, key=lambda p: pressure_score(p, planets, player), reverse=True)
    front = owned[: min(5, len(owned))]
    if not front:
        return
    for donor in sorted(my_planets, key=lambda p: budgets.get(p["id"], 0), reverse=True):
        if budgets.get(donor["id"], 0) < 35:
            continue
        if donor in front:
            continue
        target = min(front, key=lambda p: distance(donor, p))
        if pressure_score(target, planets, player) <= pressure_score(donor, planets, player) + 8:
            continue
        ships = min(budgets[donor["id"]] // 2, max(12, donor["production"] * 5))
        if ships < 10:
            continue
        if crosses_sun(donor["x"], donor["y"], target["x"], target["y"]):
            continue
        moves.append([donor["id"], angle_between(donor, target), int(ships)])
        budgets[donor["id"]] -= int(ships)
        if len(moves) >= 20:
            return


def pressure_score(planet, planets, player):
    score = planet["production"] * 4.0
    for other in planets:
        if other["owner"] == player or other["owner"] == -1:
            continue
        d = max(1.0, distance(planet, other))
        if d < 45.0:
            score += other["ships"] / d + other["production"] * (45.0 - d) / 18.0
    return score


def choose_target(
    source,
    targets,
    planets,
    player,
    available,
    planned_pressure,
    fleets,
    initial_planets,
    angular_velocity,
    comet_ids,
    comets,
    step,
):
    best = None
    for target in targets:
        if target["id"] in comet_ids and step > 420:
            continue

        pressure = planned_pressure.get(target["id"], 0)
        aim_x, aim_y = predict_position(target, max(1, min(available, target["ships"] + 1)), source, initial_planets, angular_velocity, comet_ids, comets)
        travel = distance_xy(source["x"], source["y"], aim_x, aim_y)
        friendly_fleet_count = count_friendly_fleets_to_target(target, fleets, player)
        needed = ships_needed_for_target(target, player, pressure, fleets, travel, available)
        if friendly_fleet_count >= 5 and needed <= 18:
            continue
        needed = attack_packet_size(target, needed, available, comet_ids, step)
        if needed > available:
            continue

        speed = ship_speed(needed)
        aim_x, aim_y = predict_position(target, needed, source, initial_planets, angular_velocity, comet_ids, comets)
        travel = distance_xy(source["x"], source["y"], aim_x, aim_y)
        eta = max(1.0, travel / speed)
        angle = math.atan2(aim_y - source["y"], aim_x - source["x"])

        if crosses_sun(source["x"], source["y"], aim_x, aim_y):
            continue
        score = target_score(target, source, player, needed, eta, comet_ids, step)
        if best is None or score > best[0]:
            best = (score, target, angle, int(needed))

    if best is None:
        return None
    _, target, angle, ships = best
    return target, angle, ships


def choose_opening_target(
    source,
    targets,
    available,
    initial_planets,
    angular_velocity,
    comet_ids,
    comets,
    step,
    owned_planet_count,
):
    if step > 70 or owned_planet_count > 2:
        return None
    best = None
    soften_best = None
    for target in targets:
        if target["owner"] != -1 or target["id"] in comet_ids:
            continue
        ships = target["ships"] + 1
        soft_ships = min(available, max(5, target["ships"] // 2 + 1))
        aim_x, aim_y = predict_position(target, min(ships, available), source, initial_planets, angular_velocity, comet_ids, comets)
        if crosses_sun(source["x"], source["y"], aim_x, aim_y):
            continue
        eta = distance_xy(source["x"], source["y"], aim_x, aim_y) / max(1.0, ship_speed(min(ships, available)))
        score = target["production"] * 90.0 - target["ships"] * 5.0 - eta * 4.0
        angle = math.atan2(aim_y - source["y"], aim_x - source["x"])
        if ships <= available and (best is None or score > best[0]):
            best = (score, target, angle, int(ships))
        if soft_ships <= available and target["ships"] <= available + 12:
            soft_score = score - max(0, target["ships"] - soft_ships) * 2.0
            if soften_best is None or soft_score > soften_best[0]:
                soften_best = (soft_score, target, angle, int(soft_ships))
    if best is None:
        best = soften_best
    if best is None:
        return None
    _, target, angle, ships = best
    return target, angle, ships


def ships_needed_for_target(target, player, planned_pressure, fleets, rough_travel_distance, available):
    eta = rough_travel_distance / max(1.0, ship_speed(max(1, target["ships"] + 1)))
    projected_ships = target["ships"]
    if target["owner"] != -1:
        projected_ships += int(target["production"] * min(eta, 60.0))

    friendly_arrivals = 0
    enemy_arrivals = 0
    for fleet in fleets:
        if not is_fleet_heading_to_planet(fleet, target):
            continue
        fleet_eta = distance_xy(fleet["x"], fleet["y"], target["x"], target["y"]) / ship_speed(fleet["ships"])
        if fleet_eta > eta + 5.0:
            continue
        if fleet["owner"] == player:
            friendly_arrivals += fleet["ships"]
        else:
            enemy_arrivals += fleet["ships"]
    if enemy_arrivals > available:
        enemy_arrivals = available // 2 + int((enemy_arrivals - available) ** 0.5)

    if target["owner"] == -1:
        buffer = 1
        effective_garrison = max(0, projected_ships - friendly_arrivals + enemy_arrivals)
    else:
        buffer = max(4, target["production"] * 2)
        if target["owner"] == player:
            effective_garrison = max(0, enemy_arrivals - projected_ships - friendly_arrivals)
        else:
            effective_garrison = max(0, projected_ships + enemy_arrivals - friendly_arrivals)
    return max(1, int(effective_garrison + buffer - planned_pressure))


def attack_packet_size(target, needed, available, comet_ids, step):
    if target["owner"] == -1:
        if target["id"] in comet_ids:
            minimum = 5 if step < 360 else 3
        elif step < 90:
            minimum = max(target["ships"] + 1, 12)
        else:
            minimum = max(10, 8 + target["production"] * 3)
    else:
        if step < 110:
            minimum = max(14, 10 + target["production"] * 3)
        else:
            minimum = max(24, 16 + target["production"] * 5)
    if needed < minimum and available >= minimum:
        return minimum
    return needed


def count_friendly_fleets_to_target(target, fleets, player):
    count = 0
    for fleet in fleets:
        if fleet["owner"] == player and is_fleet_heading_to_planet(fleet, target):
            count += 1
    return count


def predict_position(target, ships, source, initial_planets, angular_velocity, comet_ids, comets):
    speed = ship_speed(ships)
    eta = distance(source, target) / max(0.1, speed)
    predicted_x = target["x"]
    predicted_y = target["y"]

    if target["id"] in comet_ids:
        comet_pos = predict_comet_position(target["id"], comets, eta)
        if comet_pos is not None:
            return comet_pos
        return target["x"], target["y"]

    initial = initial_planets.get(target["id"])
    if initial is None:
        return target["x"], target["y"]

    orbit_radius = distance_xy(initial["x"], initial["y"], CENTER_X, CENTER_Y)
    if orbit_radius + initial["radius"] >= ROTATION_RADIUS_LIMIT:
        return target["x"], target["y"]

    current_angle = math.atan2(target["y"] - CENTER_Y, target["x"] - CENTER_X)
    for _ in range(4):
        future_angle = current_angle + angular_velocity * eta
        predicted_x = CENTER_X + math.cos(future_angle) * orbit_radius
        predicted_y = CENTER_Y + math.sin(future_angle) * orbit_radius
        eta = distance_xy(source["x"], source["y"], predicted_x, predicted_y) / max(0.1, speed)
    return predicted_x, predicted_y


def predict_comet_position(planet_id, comets, eta):
    for group in comets:
        ids = group.get("planet_ids", []) if isinstance(group, dict) else getattr(group, "planet_ids", [])
        if planet_id not in ids:
            continue
        index = ids.index(planet_id)
        paths = group.get("paths", []) if isinstance(group, dict) else getattr(group, "paths", [])
        path_index = group.get("path_index", 0) if isinstance(group, dict) else getattr(group, "path_index", 0)
        if index >= len(paths):
            return None
        path = paths[index]
        future_index = int(min(len(path) - 1, path_index + max(0, eta)))
        if future_index < 0 or future_index >= len(path):
            return None
        return float(path[future_index][0]), float(path[future_index][1])
    return None


def target_score(target, source, player, needed, eta, comet_ids, step):
    remaining_after_arrival = max(0.0, 500.0 - step - eta)
    if target["owner"] == -1 and step < 120:
        roi = (target["production"] * remaining_after_arrival) / max(1.0, needed + eta * 0.6)
        proximity = max(0.0, 70.0 - eta * 4.0)
        cheap_bonus = max(0.0, 25.0 - needed)
        return roi * 12.0 + proximity + cheap_bonus

    production_value = target["production"] * remaining_after_arrival
    distance_penalty = eta * (2.5 if step < 300 else 4.0)
    ship_penalty = needed * (1.0 if step < 350 else 1.7)
    neutral_bonus = 50.0 if target["owner"] == -1 and step < 250 else 10.0
    enemy_bonus = 80.0 if target["owner"] not in (-1, player) else 0.0
    comet_bonus = 30.0 if target["id"] in comet_ids and remaining_after_arrival > 80.0 else 0.0
    comet_penalty = 120.0 if target["id"] in comet_ids and remaining_after_arrival < 70.0 else 0.0
    return production_value + neutral_bonus + enemy_bonus + comet_bonus - distance_penalty - ship_penalty - comet_penalty


def blocked_by_planet(source, target, aim_x, aim_y, planets):
    start_x, start_y = point_outside_planet(source, aim_x, aim_y)
    target_distance = distance_xy(start_x, start_y, aim_x, aim_y)
    for planet in planets:
        if planet["id"] in (source["id"], target["id"]):
            continue
        if segment_distance(start_x, start_y, aim_x, aim_y, planet["x"], planet["y"]) <= planet["radius"] + 0.4:
            if distance_xy(start_x, start_y, planet["x"], planet["y"]) < target_distance:
                return True
    return False


def point_outside_planet(source, aim_x, aim_y):
    angle = math.atan2(aim_y - source["y"], aim_x - source["x"])
    return (
        source["x"] + math.cos(angle) * (source["radius"] + 0.2),
        source["y"] + math.sin(angle) * (source["radius"] + 0.2),
    )


def crosses_sun(x1, y1, x2, y2):
    return segment_distance(x1, y1, x2, y2, CENTER_X, CENTER_Y) <= SUN_RADIUS + 0.2


def segment_distance(x1, y1, x2, y2, px, py):
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return distance_xy(x1, y1, px, py)
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return distance_xy(x1 + t * dx, y1 + t * dy, px, py)


def ship_speed(ships):
    ships = max(1, ships)
    ratio = math.log(ships) / math.log(1000)
    ratio = max(0.0, min(1.0, ratio))
    return 1.0 + (MAX_SHIP_SPEED - 1.0) * (ratio ** 1.5)


def distance(a, b):
    return distance_xy(a["x"], a["y"], b["x"], b["y"])


def distance_xy(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)


def angle_between(a, b):
    return math.atan2(b["y"] - a["y"], b["x"] - a["x"])


def agent(obs):
    return orbit_wars_agent(obs)

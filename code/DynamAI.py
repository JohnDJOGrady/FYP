# Script for Dynamic AI
# Author: John O'Grady
# Version: 0.1
# Python Version: 3.72
# Requirements : python-sc2 - "pip install --user --upgrade sc2"

import random
from enum import Enum 
import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from sc2.constants import *

class StrategyPriority(Enum):
    ECONOMY = 1
    ARMY = 2
    ATTACK = 3
    RECOVER = 4
    EXPAND = 5

class UnitType(Enum):
    LIGHT = 1
    HEAVY = 2
    ANTIAIR = 3
    AIR = 4

class Behaviour():
    ideal_army_size = 0
    ideal_light = 0
    ideal_heavy = 0
    ideal_anti_air = 0
    ratio = [0,0,0]
    
    async def update_ideal_values(self, light, heavy, aa):
        self.ideal_army_size = army_size
        self.ideal_light = light
        self.ideal_heavy = heavy
        self.ideal_anti_air = aa

    async def calculate_ratio(self, light, heavy, aa):
        army = light + heavy + aa
        self.ratio[0] = army / light
        self.ratio[1] = army / heavy
        self.ratio[2] = army / aa


class DynamicBot(sc2.BotAI):
    def __init__(self):
        self.ITERATIONS_PER_MINUTE = 165
        self.MAX_DRONES = 65
        self.MAX_PER_HATCHERY = 16
        self.drone_count = 0
        self.ideal_vespene = 0
        self.strategy = StrategyPriority.ECONOMY
        self.behaviour = Behaviour

    async def on_step(self, iteration):
        # every game step execute the following coroutines
        self.iteration = iteration
        await self.increase_supply() # supply controls the number of units you can have
        await self.build_workers()
        await self.establish_vespene()
        await self.distribute_workers()
        
        # develop army
        await self.handle_upgrades()
        await self.train_units()

        # attack / defense
        await self.assault_enemy_base()

        # constructing structures
        await self.hatchery_tree()
        await self.lair_tree()
        await self.hive_tree()
        await self.defense_structures()
        await self.expand_base()
    
    # economy
    async def build_workers(self):
        if len(self.townhalls) * self.MAX_PER_HATCHERY > len(self.units(DRONE)):
            if len(self.units(DRONE)) < self.MAX_DRONES:
                larvae = self.units(LARVA)
                if larvae.exists and self.can_afford(DRONE):
                    await self.do(larvae.random.train(DRONE))

        for base in self.townhalls:
            queens = self.units(QUEEN).ready.noqueue
            if queens.exists:
                queen = queens.closest_to(base)
                if queen.distance_to(base.position) < 15.0:
                    abilities = await self.get_available_abilities(queen)
                    if AbilityId.EFFECT_INJECTLARVA in abilities:
                        await self.do(queen(EFFECT_INJECTLARVA, base))

    async def increase_supply(self):
        larvae = self.units(LARVA)
        if self.supply_left <= 4 and not self.already_pending(OVERLORD) and self.can_afford(OVERLORD):
            if larvae.exists:
                await self.do(larvae.random.train(OVERLORD)) # where should it go
    
    async def establish_vespene(self):
        for base in self.townhalls:
            if base.surplus_harvesters >= 0 or self.minerals > 500:
                geysers = self.state.vespene_geyser.closer_than(15.0, base)
                extractor_count = self.units(EXTRACTOR).amount
                ideal_extractors = self.townhalls.amount * 2
                for geyser in geysers:
                    if self.can_afford(EXTRACTOR) and extractor_count < ideal_extractors:
                        drone = self.select_build_worker(geyser.position)
                        if not self.units(EXTRACTOR).closer_than(1.0, geyser).exists:
                            extractor_count += 1
                            await self.do(drone.build(EXTRACTOR, geyser))

    async def expand_base(self):
        if self.townhalls.amount < (self.iteration / self.ITERATIONS_PER_MINUTE) and self.can_afford(HATCHERY):
            await self.expand_now()

    # structures
    async def hatchery_tree(self):
        # Spawning Pool - expands tree and allows basic units
        if not self.units(SPAWNINGPOOL).ready.exists:
            if self.can_afford(SPAWNINGPOOL) and self.workers.exists and not self.already_pending(SPAWNINGPOOL):
                hatchery = self.units(HATCHERY).ready.first
                for location in range(4, 15):
                    target = hatchery.position.to2.towards(self.game_info.map_center, location)
                    if await self.can_place(SPAWNINGPOOL, target):
                        drone = self.workers.closest_to(target)
                        invalid = await self.do(drone.build(SPAWNINGPOOL, target))
                        if not invalid:
                            break
        
        else:
            base = self.townhalls.ready.first
            # Evolution Chamber - upgrade facility
            if not self.units(EVOLUTIONCHAMBER).ready.exists:
                if self.can_afford(EVOLUTIONCHAMBER) and self.workers.exists and not self.already_pending(EVOLUTIONCHAMBER):
                    await self.build(EVOLUTIONCHAMBER, near=base)
            
            # Roach Warren - anti-heavy units
            if not self.units(ROACHWARREN).ready.exists:
                if self.can_afford(ROACHWARREN) and self.workers.exists and not self.already_pending(ROACHWARREN):
                    await self.build(ROACHWARREN, near = base)

            # Baneling Nest - anti-air / ground units
            if not self.units(BANELINGNEST).ready.exists:
                if self.can_afford(BANELINGNEST) and self.workers.exists and not self.already_pending(BANELINGNEST):
                    await self.build(BANELINGNEST, near = base)

    async def lair_tree(self):
        # hydralisk
        if self.units(LAIR).ready.exists and not self.units(HYDRALISKDEN).ready.exists:
            if self.can_afford(HYDRALISKDEN) and self.workers.exists and not self.already_pending(HYDRALISKDEN):
                lair = self.units(LAIR).ready.first
                await self.build(HYDRALISKDEN, near=lair)

    async def defense_structures(self):
        # spore crawler
        if self.units(EVOLUTIONCHAMBER).ready.exists:
            if self.can_afford(SPORECRAWLER) and self.workers.exists and self.units(SPORECRAWLER).amount < 2:
                base = self.townhalls.ready.first
                await self.build(SPORECRAWLER, near=base)

    async def hive_tree(self):
        # brutalisk
        if self.units(HIVE).ready.exists and not self.units(BRUTALISKCAVERN).ready.exists:
            if self.can_afford(BRUTALISKCAVERN) and self.workers.exists and not self.already_pending(BRUTALISKCAVERN):
                base = self.townhalls.ready.first
                await self.build(BRUTALISKCAVERN, near=base)

        # greater spire

    # unit management
    async def train_units(self):
        self.behaviour.calculate_ratio(self, self.units(ZERGLING), self.units(ROACH), self.units(HYDRALISK))
        
        if self.units(SPAWNINGPOOL).ready.exists:
            # Queen units - medic, utility, anti-air
            queens = self.units(QUEEN).ready.noqueue
            if queens.amount + self.already_pending(QUEEN) < self.townhalls.amount:
                if self.townhalls.amount < 2 or queens.amount < 1:
                    base = self.townhalls.ready.first
                    if self.can_afford(QUEEN):
                        await self.do(base.train(QUEEN))
                if queens.amount > 0:
                    bases = self.townhalls.ready.noqueue
                    for base in bases:
                        queen = queens.closest_to(base)
                        if self.can_afford(QUEEN) and queen.distance_to(base.position) > 15.0:
                            await self.do(base.train(QUEEN))

        # Roachs - anti-heavy
        if self.units(ROACHWARREN).ready.exists:
            roaches = self.units(ROACH).ready
            if roaches.amount < 5 and self.can_afford(ROACH) and self.units(LARVA).exists:
                larvae = self.units(LARVA)
                await self.do(larvae.random.train(ROACH))
        
        # Hydralisks - anti-air
        if self.units(HYDRALISKDEN).ready.exists:
            hydralisks = self.units(HYDRALISK).ready
            if hydralisks.amount < 5 and self.can_afford(HYDRALISK) and self.units(LARVA).exists:
                larvae = self.units(HYDRALISK)
                await self.do(larvae.random.train(HYDRALISK))

        # Zergling Units - anti-light
        if self.can_afford(ZERGLING) and self.units(LARVA).exists and self.behaviour.ratio[0] < 2:
            larvae = self.units(LARVA)
            await self.do(larvae.random.train(ZERGLING))

    async def handle_upgrades(self):
        if self.units(SPAWNINGPOOL).ready.exists:
            if self.can_afford(RESEARCH_ZERGLINGMETABOLICBOOST):
                pool = self.units(SPAWNINGPOOL).ready.first
                abilities = await self.get_available_abilities(pool)
                if AbilityId.RESEARCH_ZERGLINGMETABOLICBOOST in abilities:
                    await self.do(pool(RESEARCH_ZERGLINGMETABOLICBOOST))
            
            for hatchery in self.units(HATCHERY).ready:
                if hatchery.noqueue:
                    if self.can_afford(LAIR):
                        await self.do(hatchery.build(LAIR))

        if self.units(EVOLUTIONCHAMBER).ready.exists:
            chambers = self.units(EVOLUTIONCHAMBER).ready
            if chambers.amount > 0:
                for chamber in chambers:
                    abilities = await self.get_available_abilities(chamber)
                    if AbilityId.RESEARCH_ZERGMELEEWEAPONSLEVEL1 in abilities:
                        await self.do(chamber(RESEARCH_ZERGMELEEWEAPONSLEVEL1))

        if self.units(SPAWNINGPOOL).ready.exists:
            pool = self.units(SPAWNINGPOOL).ready.first


    # attacking / defending
    async def assault_enemy_base(self):
        if len(self.known_enemy_units) > 0:
            target = self.known_enemy_units.random.position
        elif len(self.known_enemy_structures) > 0:
            target = self.known_enemy_structures.random.position
        else:
            target = self.enemy_start_locations[0]
        
        attack_force = {ZERGLING: [20, 5],
                        ROACH:  [5, 3],
                        HYDRALISK: [5, 3]}

        for UNIT in attack_force:
            if self.units(UNIT).amount > attack_force[UNIT][0] and self.units(UNIT).amount > attack_force[UNIT][1]:
                for unit in self.units(UNIT).idle:
                    abilities = await self.get_available_abilities(unit)
                    if AbilityId.ATTACK_ATTACK in abilities:
                        await self.do(unit(ATTACK_ATTACK, target))

            elif self.units(UNIT).amount > attack_force[UNIT][1]:
                if len(self.known_enemy_units) > 0:
                    for unit in self.units(UNIT).idle:
                        abilities = await self.get_available_abilities(unit)
                        if AbilityId.ATTACK_ATTACK in abilities:
                            await self.do(unit(ATTACK_ATTACK, random.choice(self.known_enemy_units)))

def main():
    # run_game( maps.get(map name), [ PlayerType( Race.Race, AI class)], PlayerType(Race.Race, Difficulty.Difficulty))
    run_game(maps.get("AbyssalReefLE"), [
        Bot(Race.Zerg, DynamicBot()), 
        Computer(Race.Terran, Difficulty.Medium)
        ], realtime=False)

if __name__ == '__main__':
    main()
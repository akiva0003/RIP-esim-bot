"""Stats.py"""
import os
import statistics
from collections import defaultdict
from csv import reader, writer
from datetime import date, timedelta
from io import BytesIO, StringIO
from json import loads
from time import time
from typing import Literal, Optional

from discord import Attachment, File, Interaction
from discord.app_commands import Transform, check, checks, command, describe
from discord.ext.commands import Cog

from Help import utils
from Help.transformers import Ids, Server
from Help.utils import CoolDownModified, dmg_calculator


class Stats(Cog, command_attrs={"cooldown_after_parsing": True, "ignore_extra": False}):
    """Commands That Last Forever"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @checks.dynamic_cooldown(CoolDownModified(60))
    @command()
    @describe(at_least_10_medals="Scan all active players with at least 10 medals, instead of 100 (premium)")
    async def bhs(self, interaction: Interaction, server: Transform[str, Server], at_least_10_medals: bool = False) -> None:
        """Displays top bh medals per player in a given server."""

        if at_least_10_medals and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`at_least_10_medals` is a premium parameter! If you wish to use it, along with many other"
                             " premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `at_least_10_medals=False`",
                ephemeral=True)
            return
        await interaction.response.defer()
        base_url = f'https://{server}.e-sim.org/'
        link = f'{base_url}achievement.html?type=BH_COLLECTOR_I' if at_least_10_medals \
            else f'{base_url}achievement.html?type=BH_COLLECTOR_II'
        last_page = await utils.last_page(link)
        if last_page == 1:
            at_least_10_medals = True
            link = f'{base_url}achievement.html?type=BH_COLLECTOR_I'
            last_page = await utils.last_page(link)

        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File("files/typing.gif"))
        count = 0
        output = StringIO()
        csv_writer = writer(output)
        break_main = False
        for page in range(1, last_page):
            tree = await utils.get_content(f'{link}&page={page}')
            ids = utils.get_ids_from_path(tree, '//*[@id="esim-layout"]//div[3]//div/a')
            nicks = tree.xpath('//*[@id="esim-layout"]//div[3]//div/a/text()')
            for nick, user_id in zip(nicks, ids):
                if await self.bot.should_cancel(interaction, msg):
                    break_main = True
                    break
                count += 1
                msg = await utils.update_percent(count, (last_page - 2) * 24 + len(ids), msg)
                tree1 = await utils.get_content(f"{base_url}profile.html?id={user_id}")
                bh_medals = tree1.xpath("//*[@id='medals']//ul//li[7]//div")[0].text.replace("x", "")
                cs = tree1.xpath("//div[@class='profile-data']//div[8]//span[1]//span[1]")
                csv_writer.writerow([nick.strip(), cs[0].text if cs else "Unknown", bh_medals])
                await utils.custom_delay(interaction)
            if break_main:
                break

        output.seek(0)
        sorted_list = sorted(reader(output), key=lambda row: int(row[-1]), reverse=True)
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["#", "Nick", "Citizenship", "BHs"])
        csv_writer.writerows([[index + 1] + row for index, row in enumerate(sorted_list)])
        output.seek(0)
        msg = 'All active players with more than 10 BH medals' if at_least_10_medals else 'All active players with more than 100 BH medals'
        await utils.custom_followup(interaction, msg, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"BHs_{server}.csv")], mention_author=True)

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(ids_in_file="You must provide list/range of ids or attach a file containing the list of ids (if there are too many)",
              ids="You must provide list/range of ids or attach a file containing the list of ids (if there are too many)",
              extra_premium_info="True (premium) will take twice as long but will return much more data")
    async def convert(self, interaction: Interaction, server: Transform[str, Server], ids_in_file: Optional[Attachment],
                      ids: Optional[Transform[list, Ids]],
                      your_input_is: Literal["citizen ids", "citizen names", "military unit ids", "citizenship ids",
                                             "single MU id (get info about all MU members)"],
                      extra_premium_info: bool = False) -> None:
        """Convert ids to names and vice versa"""
        if extra_premium_info and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`extra_premium_info` is a premium parameter! If you wish to use it, along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `extra_premium_info=False`")
            return

        if not ids and not ids_in_file:
            await utils.custom_followup(
                interaction, "You must provide list/range of ids or attach a file containing the list of ids (if there are too many)",
                ephemeral=True)
            return
        if ids is None:
            ids = []
        await interaction.response.defer()
        if ids_in_file:
            ids.extend([i.decode("utf-8").split(",")[0] for i in (await ids_in_file.read()).splitlines() if i])
        key = your_input_is

        if "members" in key:
            mu_embers = await utils.get_content(f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={ids[0]}')
            ids = [str(row["id"]) for row in mu_embers]
            link = "apiCitizenById.html?id"
            name = "login"
            header = ["Id", "Nick", "citizenship", "MU id"]

        elif "citizenship" in key:
            header = ["Citizenship"]
            name = link = ""

        elif "military unit" in key:
            link = "apiMilitaryUnitById.html?id"
            name = "name"
            header = ["Id", "Name", "Total damage", "Max members", "Gold value", "Country", "Type"]

        elif key == "citizen ids":
            link = "apiCitizenById.html?id"
            name = "login"
            header = ["Id", "Nick", "citizenship", "MU id"]

        elif key == "citizen names":
            link = "apiCitizenByName.html?name"
            name = "id"
            header = ["Nick", "ID", "citizenship", "MU id"]

        else:
            await utils.custom_followup(interaction, "Key Error", ephemeral=True)
            return

        output = StringIO()
        csv_writer = writer(output)
        if extra_premium_info:
            csv_writer.writerow(["Id", "Link", "Nick", "Citizenship", "MU Id", "Last Login", "ES", "XP", "Strength",
                                 "Per limit", "Per Berserk", "Crit", "Avoid", "Miss", "Dmg", "Max", "Total Dmg",
                                 "Today's dmg", "Premium till", "", "Helmet", "Vision", "Armor", "Pants", "Shoes", "LC",
                                 "WU", "Offhand", "", "Congress medal", "CP", "Train", "Inviter", "Subs", "work", "BHs",
                                 "RW", "Tester", "Tournament"])
        else:
            csv_writer.writerow(header)
        msg = await utils.custom_followup(
            interaction, "Progress status: 1%.\n(I will update you after every 10%)" if len(ids) > 10 else
            "I'm on it, Sir. Be patient.", file=File("files/typing.gif"))
        errors = []
        index = 0
        for index, current_id in enumerate(ids):
            if await self.bot.should_cancel(interaction, msg):
                break
            if "citizenship" in key:
                csv_writer.writerow([self.bot.countries[int(current_id)]])
                continue
            if current_id == "0" or not current_id.strip():
                continue
            msg = await utils.update_percent(index, len(ids), msg)
            try:
                api = await utils.get_content(f'https://{server}.e-sim.org/{link}={current_id.lower().strip()}')
            except Exception:
                errors.append(current_id)
                continue
            if not extra_premium_info:
                if name == "name":
                    csv_writer.writerow(
                        [current_id, api[name], api["totalDamage"], api["maxMembers"], api["goldValue"],
                         self.bot.countries[api["countryId"]],
                         api["militaryUnitType"]])
                else:
                    csv_writer.writerow(
                        [current_id, api[name], api["citizenship"], api["militaryUnitId"]])

            elif api.get('id'):
                profile_link = f'https://{server}.e-sim.org/profile.html?id={api["id"]}'
                tree = await utils.get_content(profile_link)

                if api['status'] == "inactive":
                    days_number = [x.split()[-2] for x in tree.xpath('//*[@class="profile-data red"]/text()') if
                                   "This citizen has been inactive for" in x][0]
                    status = str(date.today() - timedelta(days=int(days_number)))
                elif api['status'] == "active":
                    status = ""
                else:
                    status = api['status']
                if api['premiumDays'] > 0:
                    premium = date.today() + timedelta(days=int(api['premiumDays']))
                else:
                    premium = ""
                eqs = []
                for quality in tree.xpath("//div[1]//div[2]//div[5]//tr//td[2]//div[1]//div[1]//@class"):
                    if "equipmentBack" in quality:
                        quality = quality.replace("equipmentBack q", "")
                        eqs.append(quality)
                medals1 = []
                for i in range(1, 11):
                    a = tree.xpath(f"//*[@id='medals']//ul//li[{i}]//div//text()")
                    if a:
                        medals1.append(*[x.replace("x", "") for x in a])
                    elif "emptyMedal" not in tree.xpath(f"//*[@id='medals']//ul//li[{i}]/img/@src")[0]:
                        medals1.append("1")
                    else:
                        medals1.append(0)
                strength = api['strength']
                dmg = await dmg_calculator(api=api)
                stats = {"crit": 12.5, "avoid": 5, "miss": 12.5, "dmg": 0, "max": 0}
                for eq_type, parameters, values, _ in utils.get_eqs(tree):
                    for val, p in zip(values, parameters):
                        if p in stats:
                            stats[p] += (val if p != "miss" else -val)
                stats = [round(v, 2) for v in stats.values()]
                row = [api['id'], profile_link, api['login'], api['citizenship'], api['militaryUnitId'] or "", status,
                       round(api['economySkill'], 2), api['xp'], strength, dmg["avoid"], dmg["clutch"]] + stats + [
                          api['totalDamage'] - api['damageToday'], api['damageToday'], premium, ""] + eqs + [
                          ""] + medals1
                csv_writer.writerow(row)
            await utils.custom_delay(interaction)
        output.seek(0)
        if errors:
            await utils.custom_followup(interaction, f"Couldn't convert the following: {', '.join(errors)}")
        msg = "For duplicated values, use the following excel formula: `=FILTER(A:G, COUNTIF(I2, A:A))`, where `A:G`" \
              " is the range of values in the file bellow, `I2` is the cell containing the id, and `A:A`" \
              " is the column with all ids.\nExample: <https://prnt.sc/12w4p3m> Result: <https://prnt.sc/12w4qgs>"
        await utils.custom_followup(interaction, msg, mention_author=index > 30, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"Converted_{key}_{server}.csv")])

    @checks.dynamic_cooldown(CoolDownModified(20))
    @command(name="dmg-stats")
    @describe(battles="first-last or id1, id2, id3...",
              included_countries="Example: 'Norway, Israel VS Egypt' - all battles of norway plus all Israel VS Egypt battles",
              battles_types="Check those types only (default: RWs and attacks)")
    #         extra_premium_info="True (premium) will give more data, but it will take much longer")
    # @check(utils.is_premium_level_1)
    async def dmg_stats(self, interaction: Interaction, server: Transform[str, Server], battles: Transform[list, Ids],
                        included_countries: str = "", battles_types: str = "") -> None:
        """Displays a lot of data about the given battles"""

        check_each_round = True  # TODO: temp api error
        if not await utils.is_premium_level_1(interaction, False):
            if (len(battles) > 500 and check_each_round) or (len(battles) > 1000 and not check_each_round):
                await utils.custom_followup(
                    interaction, "It's too much.. sorry. You can buy premium and remove this limit.", ephemeral=True)
                return

        correct_battle_types = ['ATTACK', 'CIVIL_WAR', 'COUNTRY_TOURNAMENT', 'CUP_EVENT_BATTLE', 'LEAGUE',
                                'MILITARY_UNIT_CUP_EVENT_BATTLE', 'PRACTICE_BATTLE', 'RESISTANCE', 'DUEL_TOURNAMENT',
                                'TEAM_NATIONAL_CUP_BATTLE', 'TEAM_TOURNAMENT', 'WORLD_WAR_EVENT_BATTLE']

        battle_types = []
        for formal_battle_type in battles_types.replace("and", ",").replace("\n", ",").split(","):
            formal_battle_type = formal_battle_type.lower().strip()
            if formal_battle_type in ("ww", "world war"):
                formal_battle_type = 'WORLD_WAR_EVENT_BATTLE'
            elif formal_battle_type in ("tournament", "country tournament", "country"):
                formal_battle_type = 'COUNTRY_TOURNAMENT'
            elif formal_battle_type in ("cw", "civil war"):
                formal_battle_type = 'CIVIL_WAR'
            elif formal_battle_type in ("rw", "resistance war"):
                formal_battle_type = 'RESISTANCE'
            elif formal_battle_type == "cup":
                formal_battle_type = 'CUP_EVENT_BATTLE'
            elif formal_battle_type == "mu cup":
                formal_battle_type = 'MILITARY_UNIT_CUP_EVENT_BATTLE'
            elif formal_battle_type == "duel":
                formal_battle_type = 'DUEL_TOURNAMENT'
            battle_types.append(formal_battle_type.strip().upper())
        for x in battle_types:
            if x not in correct_battle_types:
                await utils.custom_followup(
                    interaction, f"No such type (`{x}`). Pls choose from this list:\n" + ", ".join(
                        [f"`{i}`" for i in correct_battle_types]), ephemeral=True)
                return

        battles_types = battle_types
        if not battles_types:
            battles_types = ['ATTACK', 'RESISTANCE']

        side_count = []
        included_countries = [country.split(",") for country in included_countries.lower().split("vs")]
        if included_countries and included_countries[0][0]:
            for country in included_countries:
                side_count.append([self.bot.countries_by_name[x.strip().lower()] for x in country if x.strip()])

        await interaction.response.defer()
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)\n"
                                          f"(I have to check about {len(battles) * 2 * (11 if check_each_round else 1)} e-sim pages"
                                          f" (battles, rounds etc.), so be patient)" if len(
                                              battles) > 10 else "I'm on it, Sir. Be patient.",
                                          file=File("files/typing.gif"))
        my_dict = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0, 'limits': 0, 'medkits': 0,
                                       'last_hit': "2010-01-01 00:00:00:000", 'records': [0, 0, 0],
                                       'restores': {}})
        other_dict = defaultdict(lambda: defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0}))
        countries_dict = defaultdict(lambda: {'won': 0, 'lost': 0})
        days = []
        base_url = f"https://{server}.e-sim.org/"
        first = battles[0]
        index = battle_id = 0
        for index, battle_id in enumerate(battles):
            try:
                if await self.bot.should_cancel(interaction, msg):
                    break
                msg = await utils.update_percent(index, len(battles), msg)
                api_battles = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_id}')
                battle_restore = api_battles["type"] in (
                    'COUNTRY_TOURNAMENT', 'CUP_EVENT_BATTLE', 'MILITARY_UNIT_CUP_EVENT_BATTLE', 'TEAM_TOURNAMENT')
                defender, attacker = api_battles['defenderId'], api_battles['attackerId']
                if len(side_count) > 1:
                    condition = (any(side == defender for side in side_count[0]) and any(
                        side == attacker for side in side_count[1])) or \
                                (any(side == defender for side in side_count[1]) and any(
                                    side == attacker for side in side_count[0]))
                elif len(side_count) == 1:
                    condition = any(side in (attacker, defender) for side in side_count[0])
                else:
                    condition = True
                if not condition:
                    continue
                if battles_types and api_battles['type'] not in battles_types:
                    continue
                if attacker != defender and api_battles["type"] != "MILITARY_UNIT_CUP_EVENT_BATTLE":
                    defender, attacker = self.bot.countries.get(defender, "Defender"), self.bot.countries.get(attacker,
                                                                                                              "Attacker")

                if api_battles["type"] in ('ATTACK', 'RESISTANCE'):
                    if api_battles["attackerScore"] == 8:
                        countries_dict[attacker]['won'] += 1
                        countries_dict[defender]['lost'] += 1
                    elif api_battles["defenderScore"] == 8:
                        countries_dict[defender]['won'] += 1
                        countries_dict[attacker]['lost'] += 1
                dmg_in_battle = defaultdict(lambda: {'dmg': 0, "hits": 0})
                await utils.custom_delay(interaction)
                if api_battles['defenderScore'] == 8 or api_battles['attackerScore'] == 8:
                    last = api_battles['currentRound']
                else:
                    last = api_battles['currentRound'] + 1
                for round_id in range(1, last if check_each_round else 2):
                    sides = {'defender': 0, 'attacker': 0}
                    attacker_dmg = defaultdict(lambda: {'dmg': 0, "Clutches": 0})
                    defender_dmg = defaultdict(lambda: {'dmg': 0, "Clutches": 0})
                    dmg_in_round = defaultdict(int)
                    for hit in reversed(await utils.get_content(
                            f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_id if check_each_round else 0}')):
                        key = hit['citizenId']
                        user = my_dict[key]
                        wep = 5 if hit['berserk'] else 1

                        # TODO: consider hospitals
                        seconds_from_last = (utils.get_time(hit["time"], True) - utils.get_time(user['last_hit'],
                                                                                                True)).total_seconds()
                        full_limits = 15 + 15 + 2
                        day = hit['time'].split()[0]
                        if user['last_hit'].split()[0] != day:  # day change
                            user['limits'] = full_limits
                            user['restores'][day] = 0
                            if day not in days:
                                days.append(day)
                        if seconds_from_last > 0:
                            user['restores'][day] += 1
                            if server not in ("primera", "secura", "suna"):  # fast server has limits restore
                                user['limits'] = min(user['limits'] + int(seconds_from_last // 600) * 2 + 2, full_limits)
                        if battle_restore and user.get("has_restore"):
                            user['limits'] = 10 + 10 + 2
                            user["has_restore"] = False
                        user['limits'] -= wep * 0.6 / 5
                        if user['limits'] < -10:
                            user['medkits'] += 1
                            user['limits'] += 10 + 10
                        user['last_hit'] = hit['time']

                        user['dmg'] += hit['damage']
                        user['weps'][hit['weapon']] += wep
                        keys = [("Date", hit['time'][:10]),
                                ("MU ID", hit['militaryUnit']) if 'militaryUnit' in hit else tuple(),
                                ("Side", defender if hit['defenderSide'] else attacker),
                                ("Country", self.bot.countries[hit['citizenship']]),
                                ("Battle-Defender-Attacker",
                                 f"[url]battleStatistics.html?id={battle_id}[/url]*{defender}*{attacker}")]
                        for key1 in keys:
                            if key1:
                                other_dict[key1[0]][key1[1]]['dmg'] += hit['damage']
                                other_dict[key1[0]][key1[1]]['weps'][hit['weapon']] += wep
                        dmg_in_battle[key]["dmg"] += hit['damage']
                        dmg_in_battle[key]["hits"] += wep
                        user['records'][2] = max(user['records'][2], hit['damage'])
                        if not check_each_round or api_battles["type"] == "DUEL_TOURNAMENT":
                            continue
                        side = 'defender' if hit['defenderSide'] else 'attacker'
                        (defender_dmg if hit['defenderSide'] else attacker_dmg)[key]['dmg'] += hit['damage']
                        sides[side] += hit['damage']
                        dmg_in_round[key] += hit['damage']

                    if not check_each_round or api_battles["type"] == "DUEL_TOURNAMENT":
                        continue
                    if sides['attacker'] > sides['defender']:
                        for key, value in attacker_dmg.items():
                            if sides['attacker'] - value['dmg'] < sides['defender']:
                                value['Clutches'] += 1
                    else:
                        for key, value in defender_dmg.items():
                            if sides['defender'] - value['dmg'] < sides['attacker']:
                                value['Clutches'] += 1

                    for d in (attacker_dmg, defender_dmg):
                        for key, value in d.items():
                            if value['Clutches']:
                                if 'Clutches' not in my_dict[key]:
                                    my_dict[key]['Clutches'] = 0
                                my_dict[key]['Clutches'] += value['Clutches']

                        if d:
                            bh = max(d.items(), key=lambda x: x[1]["dmg"])[0]
                            if 'bhs' not in my_dict[bh]:
                                my_dict[bh]['bhs'] = 0
                            my_dict[bh]['bhs'] += 1

                    for k, v in dmg_in_round.items():
                        my_dict[k]['records'][1] = max(my_dict[k]['records'][1], v)
                    await utils.custom_delay(interaction)
                for k, v in dmg_in_battle.items():
                    my_dict[k]['records'][0] = max(my_dict[k]['records'][0], v["dmg"])
                    if battle_restore and v["hits"] >= 30:
                        my_dict[k]["has_restore"] = True

            except Exception as error:
                await utils.send_error(interaction, error, battle_id)
                break

        output = StringIO()
        csv_writer = writer(output)
        if check_each_round:
            csv_writer.writerow(
                ["Citizen id", "Dmg", "medkits used (rough estimation)", "Clutches", "BHs", "Q0 wep", "Q1", "Q2", "Q3",
                 "Q4", "Q5 wep", "Best dmg in 1 battle", "Best dmg in 1 round", "Best hit"])
            for k, v in sorted(my_dict.items(), key=lambda x: x[1]["dmg"], reverse=True):
                csv_writer.writerow([k, v["dmg"], v["medkits"], v.get("Clutches", ""), v.get("bhs", "")] +
                                    [x or "" for x in v["weps"]] + v["records"])
        else:
            csv_writer.writerow(["Citizen id", "Dmg", "medkits used (rough estimation)", "Q0 wep", "Q1", "Q2", "Q3",
                                 "Q4", "Q5 wep", "Best dmg in 1 battle", "Best hit"])
            for k, v in sorted(my_dict.items(), key=lambda x: x[1]["dmg"], reverse=True):
                csv_writer.writerow([k, v["dmg"], v["medkits"]] + [x or "" for x in v["weps"]] + v["records"][::2])

        output1 = StringIO()
        csv_writer = writer(output1)
        other_dict["Country-Battles won-Battles lost"].update(countries_dict)
        for header, v in other_dict.items():
            if header == "Country-Battles won-Battles lost":
                sorting_key = "won"
                csv_headers = ["#", *(header.split("-")[:-1]), header.split("-")[-1]]
            else:
                sorting_key = "dmg"
                csv_headers = ["#", *(header.split("-")), "DMG", "Q0", "Q1", "Q2", "Q3", "Q4", "Q5"]
            csv_writer.writerow(csv_headers)
            for num, [k, v] in enumerate(sorted(v.items(), key=lambda kv: kv[1][sorting_key], reverse=True)):
                if header == "Country-Battles won-Battles lost":
                    row = [str(num + 1), k,
                           f"{v['won']}\\n({round(round(v['won'] / (v['won'] + v['lost']), 2) * 100)}%)",
                           f"{v['lost']}\\n({round(round(v['lost'] / (v['won'] + v['lost']), 2) * 100)}%)"]
                    csv_writer.writerow(row)
                else:
                    row = [str(num + 1), *str(k).split("*"), v["dmg"]] + [x or "" for x in v["weps"]]
                    csv_writer.writerow(row)
            if header != list(other_dict.keys())[-1]:
                csv_writer.writerow([""])
                csv_writer.writerow(["-"] * len(csv_headers))
                csv_writer.writerow([""])

        output2 = StringIO()
        csv_writer = writer(output2)
        csv_writer.writerow(["Restores used per user id and day", "Average Per Day", "Median", "Max"] + days)
        for k, v in my_dict.items():
            csv_writer.writerow(
                [k, round(statistics.mean(v["restores"].values())), round(statistics.median(v["restores"].values())),
                 max(v["restores"].values())] + [v["restores"].get(day, "") for day in days])

        output.seek(0)
        output1.seek(0)
        output2.seek(0)

        await utils.custom_followup(interaction, mention_author=index > 50, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=await utils.csv_to_image(output1), filename=f"Preview1_{server}.png"),
            File(fp=await utils.csv_to_image(output2), filename=f"Preview2_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"PlayersDmg_{first}_{battle_id}_{server}.csv"),
            File(fp=BytesIO(output1.getvalue().encode()), filename=f"CountriesDmg_{first}_{battle_id}_{server}.csv"),
            File(fp=BytesIO(output2.getvalue().encode()), filename=f"RestoresCount_{first}_{battle_id}_{server}.csv")])

    @command(name="drops-stats")
    @check(utils.is_premium_level_1)
    @describe(battles="first-last or id1, id2, id3...")
    async def drops_stats(self, interaction: Interaction, server: Transform[str, Server],
                          battles: Transform[list, Ids]) -> None:
        """Shows drops distribution per player in the given battles."""

        await interaction.response.defer()
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if len(
                                              battles) > 10 else "I'm on it, Sir. Be patient.",
                                          file=File("files/typing.gif"))

        base_url = f'https://{server}.e-sim.org/'
        lucky = False
        index = current_id = 0
        filename = f"temp_files/{time()}.csv"
        f = open(filename, "w", newline="")
        csv_writer = writer(f)
        for index, current_id in enumerate(battles):
            my_dict = defaultdict(lambda: {"Q": [0, 0, 0, 0, 0, 0]})
            try:
                if await self.bot.should_cancel(interaction, msg):
                    break
                msg = await utils.update_percent(index, len(battles), msg)
                battle_link = f'{base_url}battleDrops.html?id={current_id}'
                last_page = await utils.last_page(battle_link)
                for page in range(1, last_page):
                    tree = await utils.get_content(battle_link + f'&page={page}')
                    qualities = tree.xpath("//tr[position()>1]//td[2]/text()")
                    items = [x.strip() for x in tree.xpath("//tr[position()>1]//td[3]/text()")]
                    nicks = [x.strip() for x in tree.xpath("//tr[position()>1]//td[4]//a/text()")]
                    links = [f"{base_url}battle.html?id={x}" for x in
                             utils.get_ids_from_path(tree, "//tr[position()>1]//td[4]//a")]
                    for nick, link, quality, item in zip(nicks, links, qualities, items):
                        my_dict[(nick, link)]["Q"][int(quality.replace("Q", "")) - 1] += 1
                        if item == "Lucky charm":
                            lucky = True
                            if "LC" not in my_dict[(nick, link)]:
                                my_dict[(nick, link)]["LC"] = [0, 0, 0, 0, 0, 0]
                            my_dict[(nick, link)]["LC"][int(quality.replace("Q", "")) - 1] += 1

                battle_link = f'{base_url}battleDrops.html?id={current_id}&showSpecialItems=yes'
                last_page = await utils.last_page(battle_link)
                for page in range(1, last_page):
                    tree = await utils.get_content(battle_link + f'&page={page}')
                    nicks = [x.strip() for x in tree.xpath("//tr[position()>1]//td[2]//a/text()")]
                    links = [f"{base_url}battle.html?id={x}" for x in
                             utils.get_ids_from_path(tree, "//tr[position()>1]//td[2]//a")]
                    items = [x.strip() for x in tree.xpath("//tr[position()>1]//td[1]//text()") if x.strip()]
                    for nick, link, item in zip(nicks, links, items):
                        if "elixir" in item:
                            key = "elixir"
                        elif "Bandage size " in item:
                            key = "bandage"
                        else:
                            key = item.replace("Equipment parameter ", "").replace(
                                "Camouflage ", "").replace(" class", "")
                        if key not in my_dict[(nick, link)]:
                            my_dict[(nick, link)][key] = 0
                        my_dict[(nick, link)][key] += 1
            except Exception as error:
                await utils.send_error(interaction, error, current_id)
                break
            for k, v in my_dict.items():
                row = list(k) + [x or "0" for x in v["Q"]] + [
                    v.get("upgrade", "0"), v.get("reshuffle", "0"), v.get("elixir", "0"), v.get("1st", "0"),
                    v.get("2nd", "0"), v.get("3rd", "0"), v.get("bandage", "0")] + v.get("LC", [])
                csv_writer.writerow(row)
            await utils.custom_delay(interaction)
        f.close()
        my_dict = {}
        with open(filename, 'r') as csvfile:
            csv_reader = reader(csvfile)
            for row in csv_reader:
                nick = (row[0], row[1])
                if nick in my_dict:
                    for i in range(len(my_dict[nick])-2):
                        my_dict[nick][i] += int(row[i+2])
                else:
                    my_dict[nick] = [int(x) for x in row[2:]]

        headers = ["Nick", "Link", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Upgrade", "Reshuffle", "Elixir",
                   "Camouflage 1st class", "2nd", "3rd", "Bandage"]
        if lucky:
            headers += ["Q1 LC", "Q2 LC", "Q3 LC", "Q4 LC", "Q5 LC", "Q6 LC"]
        with open(filename, 'w', newline='') as csvfile:
            csv_writer = writer(csvfile)
            csv_writer.writerow(headers)
            for nick, row in my_dict.items():
                csv_writer.writerow(list(nick) + [str(x) if x else "" for x in row])
        if my_dict:
            await utils.custom_followup(interaction, mention_author=index > 100, file=File(
                filename, filename=f"Drops_{battles[0]}_{current_id}_{server}.csv"))
        else:
            await utils.custom_followup(interaction, "No drops were found")
        os.remove(filename)

    @checks.dynamic_cooldown(CoolDownModified(60))
    @command()
    @describe(server="You can see you score using /calc with bonuses=as new player",
              scan_more_players="True (premium) - all players with EQUIPPED_V achievement, otherwise - LEGENDARY_EQUIPMENT")
    async def sets(self, interaction: Interaction, server: Transform[str, Server], scan_more_players: bool = False) -> None:
        """Displays top avoid and clutch sets per player in a given server."""

        if scan_more_players and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`scan_more_players` is a premium parameter! If you wish to use it, along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `scan_more_players=False`", ephemeral=True)
            return

        await interaction.response.defer()
        base_url = f'https://{server}.e-sim.org/'
        output = StringIO()
        csv_writer = writer(output)
        link = f'{base_url}achievement.html?type=EQUIPPED_V' if scan_more_players else f'{base_url}achievement.html?type=LEGENDARY_EQUIPMENT'
        last_page = await utils.last_page(link)
        if last_page == 1:
            scan_more_players = True
            link = f'{base_url}achievement.html?type=EQUIPPED_V'
            last_page = await utils.last_page(link)
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File("files/typing.gif"))
        count = 0
        for page in range(1, last_page):
            tree = await utils.get_content(f'{link}&page={page}')
            links = utils.get_ids_from_path(tree, '//*[@id="esim-layout"]//div[3]//div/a')
            for user_id in links:
                count += 1
                msg = await utils.update_percent(count, (last_page - 2) * 24 + len(links), msg)
                api = await utils.get_content(f"{base_url}apiCitizenById.html?id={user_id}")
                dmg = await dmg_calculator(api)
                csv_writer.writerow([api["login"], api['citizenship'], api['eqCriticalHit'], api['eqReduceMiss'],
                                     api['eqAvoidDamage'], api['eqIncreaseMaxDamage'], api['eqIncreaseDamage'],
                                     dmg["avoid"], dmg["clutch"], api['eqIncreaseEcoSkill']])
                await utils.custom_delay(interaction)

        output.seek(0)
        sorted_list = sorted(reader(output), key=lambda row: int(row[-3]), reverse=True)
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(
            ["#", "Nick", "Citizenship", "Crit", "Miss", "Avoid", "Max", "Dmg", "Per limit", "Per berserk", "Eco"])
        csv_writer.writerows([[index + 1] + row for index, row in enumerate(sorted_list)])
        output.seek(0)
        msg = "Only players that have ever had Q5 EQ" if scan_more_players else \
            "Only active players that have ever worn more than 5 Q6 EQ's at the same time. "
        await utils.custom_followup(interaction, msg, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_sets_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"Sets_{server}.csv")], mention_author=True)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(custom_api="API containing simple json (single dictionary or single list)")
    async def table(self, interaction: Interaction, server: Transform[str, Server], custom_api: str = "") -> None:
        """Converts simple json to csv table."""

        if custom_api and "http" not in custom_api:
            await utils.custom_followup(interaction, f"{custom_api} is not a valid link", ephemeral=True)
            return
        await interaction.response.defer()
        if ".e-sim.org/battle.html?id=" in custom_api:
            if "round" in custom_api:
                custom_api = custom_api.replace("battle", "apiFights").replace("id", "battleId").replace("round", "roundId")
            else:
                custom_api = custom_api.replace("battle", "apiBattles").replace("id", "battleId")
        if ".e-sim.org/" in custom_api and not custom_api.startswith(self.bot.api) and "api" not in custom_api:
            custom_api = self.bot.api + custom_api.replace("//", "/")
        files = []
        base_url = f"https://{server}.e-sim.org/"
        links = ["apiRegions", "apiMap", "apiRanks", "apiCountries", "apiOnlinePlayers"]
        for link in links if not custom_api else [custom_api]:
            api = await utils.get_content((base_url + link + ".html") if not custom_api else custom_api,
                                          return_type="json", throw=True)
            if link == "apiOnlinePlayers":
                api = [loads(row) for row in api]
            if not api:
                await utils.custom_followup(interaction, "Nothing found.")
                return
            api = api if isinstance(api, list) else [api]
            lists_headers = [k for k, v in api[0].items() if isinstance(v, list)]
            headers = [k for k, v in api[0].items() if not isinstance(v, list)]
            headers = await update_missing_keys(link, headers)
            output = StringIO()
            csv_writer = writer(output)
            csv_writer.writerow(headers)
            for row in api:
                csv_writer.writerow([row.get(header, "") for header in headers])

                for header in lists_headers:
                    value = row.get(header, "")
                    if not value:
                        continue
                    if not isinstance(value[0], dict):
                        csv_writer.writerow([header])
                        csv_writer.writerow(value)
                        continue

                    inner_headers = list(value[0].keys())
                    csv_writer.writerow([])
                    csv_writer.writerow([header])
                    if len(inner_headers) < 10:
                        csv_writer.writerow(inner_headers)
                        for inner_row in value:
                            csv_writer.writerow([inner_row.get(inner_header, "") for inner_header in inner_headers])
                    else:
                        for inner_row in value:
                            csv_writer.writerows(
                                [(inner_header, inner_row.get(inner_header, "")) for inner_header in inner_headers])
                    csv_writer.writerow([])

            output.seek(0)
            files.append(File(fp=BytesIO(output.getvalue().encode()), filename=f"{link}_{server}.csv"))
            await utils.custom_delay(interaction)

        await utils.custom_followup(interaction, files=files)


async def update_missing_keys(link: str, headers: list) -> list:
    """update missing keys"""
    missing = {'apiRegions': ['resource'], 'apiMap': ['battleId', 'raw'], 'apiCountries': ['president'],
               'apiMilitaryUnitMembers': ['companyId'],
               'apiFights': ['dsQuality', 'militaryUnitBonus', 'localizationBonus', 'militaryUnit']}
    for k, v in missing.items():
        if k in link:
            for key in v:
                if key not in headers:
                    headers.append(key)
    return headers


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Stats(bot))

# Obra Dinn id 速查表（从 txtAssetDump 自动生成）

游戏版本：`1.2.122`　生成脚本：`parse_assets.py`

## 1. `fateId` 的 base 全集

共 **48** 个（来自 TextAsset `FateBaseIds`）。
完整语法：`baseId` 或 `baseId:killerId`，冒号仅当 baseId 含 `-killer` 时出现。

| 类别 | 数量 | 取值 |
|---|---|---|
| 特殊 | 1 | `unknown` |
| 他杀（`-killer`，可带 `:凶手`） | 13 | `arrowed-killer`, `gunned-killer`, `cannoned-killer`, `knifed-killer`, `sworded-killer`, `clubbed-killer`, `axed-killer`, `speared-killer`, `dismembered-killer`, `decapitated-killer`, `drowned-killer`, `eaten-killer`, `strangled-killer` |
| 海怪致死（`-beast`） | 6 | `spiked-beast`, `clawed-beast`, `winged-beast`, `tailed-beast`, `hooved-beast`, `crushed-beast` |
| 挤压（`crushed-`） | 4 | `crushed-cargo`, `crushed-cannon`, `crushed-rigging`, `crushed-stones` |
| 坠落（`fell-`） | 3 | `fell-stairs`, `fell-rigging`, `fell-overboard` |
| 自然/病死（`expired-`） | 2 | `expired-age`, `expired-sick` |
| 事故/其他 | 5 | `exploded`, `electrocuted`, `poisoned`, `burned`, `froze` |
| 自杀（`suicide-`） | 4 | `suicide-gun`, `suicide-knife`, `suicide-spear`, `suicide-noose` |
| 存活/去向（`alive-`） | 10 | `alive-uk`, `alive-eastindies`, `alive-westindies`, `alive-middleeast`, `alive-europe`, `alive-africa`, `alive-island`, `alive-canary`, `alive-verde`, `alive-azores` |

## 2. `killerId` 的合法取值（`FateEntIds`）

共 **69** 个。

| 类别 | 数量 | 说明 | 取值 |
|---|---|---|---|
| 特殊 | 3 | `unknown` 无凶手；`beast` 海怪；`enemy` 敌人（非船员） | `unknown`, `enemy`, `beast` |
| 职级（`?` 前缀） | 6 | **只知职级、不知是谁** —— 与 `Crew.category` 列同源 | `?officer`, `?pass`, `?stew`, `?mid`, `?top`, `?sea` |
| 具体船员 | 60 | | `captain`, `mate1`, `mate2`, `mate3`, `mate4`, `bosun`, `bosunmate`, `surgeon`, `surgeonmate`, `carp`, `carpmate`, `cook`, `butcher`, `gunner`, `gunnermate`, `purser`, `sea9`, `pass5`, `pass1`, `pass2`, `pass3`, `pass4`, `pass6`, `pass7`, `pass8`, `pass9`, `stewship`, `stewcap`, `stewm1`, `stewm2`, `stewm3`, `stewm4`, `mid1`, `mid2`, `mid3`, `top5`, `top6`, `top1`, `top4`, `top7`, `top8`, `top9`, `top3`, `topa`, `top2`, `sea1`, `sea5`, `sea2`, `sea3`, `sea6`, `sea4`, `sea7`, `sea8`, `seac`, `seaa`, `seab`, `sead`, `seae`, `seaf`, `seag` |

> `FateEntIds` 里的具体船员 id 共 60 个，与存档里 60 个 `face.id` 的关系：少 0 个（`face.id` 全集见 §3）。

## 3. 船员名册（`Crew` 表，60 人）

| id | job | category | difficulty | pay | 可接受的命运答案 | clue 时刻 |
|---|---|---|---|---|---|---|
| `captain` | captain | `?officer` | easy | 120 | `suicide-gun` | mate1 |
| `mate1` | mate1 | `?officer` | easy | 90 | `gunned-killer:captain` | | captain bosun |
| `mate2` | mate2 | `?officer` | easy | 80 | `gunned-killer:pass8` | | pass2 stewm2 |
| `mate3` | mate3 | `?officer` | — | 70 | `speared-killer:beast`<br>`spiked-beast` | pass1 |
| `mate4` | mate4 | `?officer` | — | 70 | `clubbed-killer:seab` | mate2 |
| `bosun` | bosun | `?officer` | — | 60 | `dismembered-killer:beast` | bosun |
| `bosunmate` | bosunmate | `?officer` | hard | 40 | `dismembered-killer:beast`<br>`crushed-beast`<br>`drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | | pass8 top9 |
| `surgeon` | surgeon | `?officer` | — | 60 | `alive-africa` | sea4 |
| `surgeonmate` | surgeonmate | `?officer` | — | 40 | `decapitated-killer:beast`<br>`clawed-beast`<br>`strangled-killer:beast` | sea4 |
| `carp` | carp | `?officer` | hard | 50 | `speared-killer:beast`<br>`spiked-beast`<br>`clawed-beast` | & sea8 carpmate |
| `carpmate` | carpmate | `?officer` | hard | 30 | `speared-killer:beast`<br>`spiked-beast` | & sea8 carpmate |
| `cook` | cook | `?officer` | — | 40 | `clubbed-killer:beast`<br>`tailed-beast`<br>`crushed-beast` | cook |
| `butcher` | butcher | `?officer` | — | 30 | `speared-killer:beast`<br>`spiked-beast` | cow |
| `gunner` | gunner | `?officer` | easy | 60 | `cannoned-killer:beast`<br>`cannoned-killer:sea7`<br>`exploded` | pass9 |
| `gunnermate` | gunnermate | `?officer` | — | 50 | `gunned-killer:mate4` | & pass9 stewship |
| `purser` | purser | `?officer` | — | 60 | `drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | stewship |
| `sea9` | helm | `?officer` | — | 30 | `dismembered-killer:beast`<br>`crushed-beast`<br>`drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | - |
| `pass5` | artist | `?officer` | easy | 50 | `crushed-beast`<br>`strangled-killer:beast` | - |
| `pass1` | pass | `?pass` | easy | 0 | `crushed-beast`<br>`crushed-rigging`<br>`clubbed-killer:beast` | | captain pass1 |
| `pass2` | pass | `?pass` | easy | 0 | `knifed-killer:mate2` | pass2 |
| `pass3` | pass | `?pass` | hard | 0 | `alive-africa` | pass1 |
| `pass4` | pass | `?pass` | hard | 0 | `alive-africa` | pass1 |
| `pass6` | pass | `?pass` | easy | 0 | `strangled-killer:beast`<br>`clawed-beast` | | pass9 pass7 |
| `pass7` | pass | `?pass` | easy | 0 | `burned`<br>`poisoned`<br>`electrocuted` | seae |
| `pass8` | pass | `?pass` | hard | 0 | `speared-killer:beast`<br>`spiked-beast` | & seae pass9 |
| `pass9` | pass | `?pass` | easy | 0 | `gunned-killer:seab` | pass9 |
| `stewship` | stewship | `?stew` | hard | 35 | `gunned-killer:bosunmate` | stewship |
| `stewcap` | stewcap | `?stew` | — | 45 | `burned`<br>`poisoned`<br>`electrocuted` | sea6 |
| `stewm1` | stewm1 | `?stew` | easy | 35 | `sworded-killer:top2` | stewm1 |
| `stewm2` | stewm2 | `?stew` | hard | 35 | `knifed-killer:pass7` | | pass2 stewm2 |
| `stewm3` | stewm3 | `?stew` | — | 10 | `crushed-cannon` | pass5 |
| `stewm4` | stewm4 | `?stew` | hard | 10 | `alive-africa` | & mate2 | pass9 pass5 |
| `mid1` | mid | `?mid` | — | 30 | `exploded` | mid2 |
| `mid2` | mid | `?mid` | hard | 30 | `knifed-killer:gunnermate` | cow |
| `mid3` | mid | `?mid` | easy | 30 | `burned`<br>`spiked-beast`<br>`speared-killer:beast`<br>`sworded-killer:mid1` | cow |
| `top5` | top | `?top` | hard | 25 | `fell-overboard`<br>`drowned-killer:beast` | & pass5 surgeonmate |
| `top6` | top | `?top` | hard | 25 | `gunned-killer:mate2` | & seac top6 |
| `top1` | top | `?top` | hard | 25 | `electrocuted` | & seac | pass9 | pass8 top1 |
| `top4` | top | `?top` | hard | 25 | `decapitated-killer:beast`<br>`clawed-beast`<br>`strangled-killer:beast` | & seac surgeonmate |
| `top7` | top | `?top` | hard | 25 | `speared-killer:beast`<br>`spiked-beast` | & pass5 & seac | pass9 top7 |
| `top8` | top | `?top` | — | 25 | `dismembered-killer:beast`<br>`crushed-beast`<br>`drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | pass5 |
| `top9` | top | `?top` | easy | 25 | `speared-killer:beast`<br>`spiked-beast` | top9 |
| `top3` | top | `?top` | — | 25 | `dismembered-killer:beast`<br>`crushed-beast` | top3 |
| `topa` | top | `?top` | hard | 25 | `clubbed-killer:captain`<br>`speared-killer:captain` | & seac pass5 |
| `top2` | top | `?top` | hard | 25 | `gunned-killer:pass3` | & seac | pass5 top1 |
| `sea1` | sea | `?sea` | hard | 15 | `drowned-killer:beast`<br>`strangled-killer:beast`<br>`clawed-beast`<br>`fell-overboard` | & & seac | stewm2 top6 | top1 pass5 |
| `sea5` | sea | `?sea` | hard | 15 | `drowned-killer:beast`<br>`strangled-killer:beast`<br>`clawed-beast`<br>`fell-overboard` | & seac | stewm2 top6 |
| `sea2` | sea | `?sea` | hard | 15 | `drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | sea3 |
| `sea3` | sea | `?sea` | easy | 15 | `clubbed-killer:sea2` | sea3 |
| `sea6` | sea | `?sea` | easy | 15 | `sworded-killer:stewcap`<br>`dismembered-killer:stewcap` | sea6 |
| `sea4` | sea | `?sea` | easy | 15 | `expired-sick` | seac |
| `sea7` | sea | `?sea` | hard | 15 | `crushed-beast`<br>`crushed-cannon` | seac |
| `sea8` | sea | `?sea` | — | 15 | `crushed-beast`<br>`crushed-cargo`<br>`fell-stairs` | seac |
| `seac` | sea | `?sea` | easy | 15 | `expired-sick` | seac |
| `seaa` | sea | `?sea` | hard | 15 | `speared-killer:beast`<br>`spiked-beast` | & sea8 sea3 |
| `seab` | sea | `?sea` | easy | 15 | `knifed-killer:captain` | mid2 |
| `sead` | sea | `?sea` | hard | 15 | `drowned-killer:beast`<br>`fell-overboard`<br>`eaten-killer:beast` | & sea3 stewship |
| `seae` | sea | `?sea` | — | 15 | `speared-killer:beast`<br>`spiked-beast` | & seac stewm2 |
| `seaf` | sea | `?sea` | hard | 15 | `cannoned-killer:beast`<br>`cannoned-killer:sea7`<br>`exploded`<br>`fell-overboard`<br>`eaten-killer:beast`<br>`drowned-killer:beast` | & seac pass5 |
| `seag` | sea | `?sea` | hard | 15 | `crushed-cargo` | & sea3 seag |

> **34 个**船员的命运答案**不唯一**（`IsCorrectFate` 用 `Contains` 判定），最多的是 `seaf`（6 个答案）。

## 4. `moment.id` 与章节（`Moments` 表，49 个）

| moment id | 章节 | 死者 | 尸体 | 音乐 |
|---|---|---|---|---|
| `d000-stow-m00-seag` | `d000` | `seag` | — | 01 Loose Cargo B |
| `d000-stow-m01-stowaway` | `d000` | `-` | moved | 01 Loose Cargo A |
| `d010-cold-m00-seac` | `d010` | `seac` | moved | 02 A Bitter Cold A |
| `d010-cold-m01-sea4` | `d010` | `sea4` | moved | 02 A Bitter Cold B |
| `d010-cold-m02-cow` | `d010` | `-` | — | 02 A Bitter Cold A |
| `d020-shel-m00-pass2` | `d020` | `pass2` | moved | 03 Murder B |
| `d020-shel-m02-pass9` | `d020` | `pass9` | — | 03 Murder A |
| `d020-shel-m03-top6` | `d020` | `top6` | moved | 03 Murder B |
| `d030-laun-m00-top7` | `d030` | `top7` | inceptive | 04 The Calling A |
| `d030-laun-m01-seae` | `d030` | `seae` | inceptive | 04 The Calling B |
| `d030-laun-m02-stewm2` | `d030` | `stewm2` | inceptive | 04 The Calling A |
| `d030-laun-m03-pass6` | `d030` | `pass6` | moved | 04 The Calling B |
| `d030-laun-m04-pass7` | `d030` | `pass7` | moved | 04 The Calling A |
| `d030-laun-m05-mate2` | `d030` | `mate2` | moved | 04 The Calling B |
| `d040-merm-m00-pass8` | `d040` | `pass8`, `seaa` | — | 05 Unholy Captives B |
| `d040-merm-m01-cook` | `d040` | `cook` | — | 05 Unholy Captives A |
| `d040-merm-m02-sea8` | `d040` | `sea8` | — | 05 Unholy Captives B |
| `d040-merm-m03-sea6` | `d040` | `sea6` | — | 05 Unholy Captives A |
| `d050-ride-m00-top1` | `d050` | `top1` | — | 06 Soldiers of the Sea A |
| `d050-ride-m01-top9` | `d050` | `top9` | — | 06 Soldiers of the Sea C |
| `d050-ride-m02-carpmate` | `d050` | `carpmate` | — | 06 Soldiers of the Sea A |
| `d050-ride-m03-surgeonmate` | `d050` | `surgeonmate`, `top4` | — | 06 Soldiers of the Sea C |
| `d050-ride-m04-mid3` | `d050` | `mid3` | — | 06 Soldiers of the Sea A |
| `d050-ride-m05-butcher` | `d050` | `butcher` | — | 06 Soldiers of the Sea C |
| `d050-ride-m06-stewship` | `d050` | `stewship` | — | 06 Soldiers of the Sea A |
| `d050-ride-m07-carp` | `d050` | `carp` | moved | 06 Soldiers of the Sea A |
| `d060-krak-m00-sea3` | `d060` | `sea3` | — | 07 The Doom B |
| `d060-krak-m01-pass5` | `d060` | `pass5` | — | 07 The Doom A |
| `d060-krak-m02-sea7` | `d060` | `sea7` | — | 07 The Doom B |
| `d060-krak-m03-gunner` | `d060` | `gunner`, `seaf` | — | 07 The Doom A |
| `d060-krak-m04-stewm3` | `d060` | `stewm3` | — | 07 The Doom B |
| `d060-krak-m05-mid1` | `d060` | `mid1` | — | 07 The Doom A |
| `d060-krak-m06-top3` | `d060` | `top3` | — | 07 The Doom B |
| `d060-krak-m07-pass1` | `d060` | `pass1` | moved | 07 The Doom A |
| `d070-save-m00-stewcap` | `d070` | `stewcap` | inceptive | 08 Bargain B |
| `d070-save-m01-mermaid3` | `d070` | `-` | inceptive | 08 Bargain D |
| `d070-save-m02-mermaid2` | `d070` | `-` | inceptive | 08 Bargain C |
| `d070-save-m03-mate3` | `d070` | `mate3` | inceptive | 08 Bargain B |
| `d070-save-m04-monkey` | `d070` | `-` | — | 08 Bargain A |
| `d080-esca-m00-bosun` | `d080` | `bosun` | — | 09 Escape B |
| `d080-esca-m01-stewm1` | `d080` | `stewm1` | — | 09 Escape A |
| `d080-esca-m02-top2` | `d080` | `top2` | — | 09 Escape B |
| `d080-esca-m03-gunnermate` | `d080` | `gunnermate` | — | 09 Escape A |
| `d080-esca-m04-mate4` | `d080` | `mate4` | — | 09 Escape B |
| `d080-esca-m05-mid2` | `d080` | `mid2` | — | 09 Escape A |
| `d090-fate-m00-mate1` | `d090` | `mate1` | — | 10 The End A |
| `d090-fate-m01-seab` | `d090` | `seab` | — | 10 The End B |
| `d090-fate-m02-topa` | `d090` | `topa` | — | 10 The End A |
| `d090-fate-m03-captain` | `d090` | `captain` | — | 10 The End B |

> 另有硬编码的 `d100-fina-m00-final`，不进存档的 `moments` 列表（`isFinal`），所以存档里是 49 条。

## 5. `disaster.id` → 章节名

| disaster id | moment 数 | 章节名（来自 `Lang` 键 `book_chapter_N_name`） |
|---|---|---|
| `d000` | 2 | Loose Cargo |
| `d010` | 3 | A Bitter Cold |
| `d020` | 3 | Murder |
| `d030` | 6 | The Calling |
| `d040` | 4 | Unholy Captives |
| `d050` | 8 | Soldiers of the Sea |
| `d060` | 8 | The Doom |
| `d070` | 5 | Bargain |
| `d080` | 6 | Escape |
| `d090` | 4 | The End |

## 6. `Presence` 表（每时刻在场名单）

共 56 个 moment 有记录。
其中 7 个 id **不在** `Moments` 表里（`Story.GetMoment()` 返回 `null` 会被跳过），属遗留条目：

- `d005-sket-m00-sk_dance`
- `d005-sket-m01-sk_princess`
- `d020-shel-m01-sk_justice`
- `d080-esca-m00-stewm1`
- `d080-esca-m01-top2`
- `d080-esca-m02-bosun`
- `d100-fina-m00-final`

## 7. 端到端验证（`validate_ids.py`）

用本表的答案集合复现游戏的判定逻辑（`savedata.css:622`）：

```csharp
if (faceData.id == faceData.nameId && Manifest.it.IsCorrectFate(crewId, faceData.fateId))
    // 判定正确
```

即 `markedCorrect == (nameId == id) && (fateId ∈ crew.fateIds)`。核对三份存档共 **180** 条 `face` 记录：

| 指标 | 结果 |
|---|---|
| 判定吻合 | **180 / 180 = 100%** |
| `fateId` 落在 `FateBaseIds`/`FateEntIds` 词表外的记录 | **0** |

⇒ `fateId` 语法、`killerId` 词表、每题答案集合、`markedCorrect`、`nameId` 五个语义**全部验证通过**。

## 8. 未使用的遗留资产

`txtAssetDump` 里这几张表**在全部 370 个源码文件中都没有被 `Resources.Load` 引用**：

| 表 | 内容 | 判断 |
|---|---|---|
| `Action-Action` | 旧式死因 → 英文标签，如 `killed-gun` → `Shot (Gun)` | **遗留**：命名属旧一代方案 |
| `Verb-Table` | 旧式动词 → 宾语槽位，如 `killed-gun` → `killer` | 同上 |
| `Object-Table` | 旧式 `killer.?officer` / `killer.beast` 模板 | 同上 |
| `Subject-Table` | 旧式 `$num\|$name\|$job\|$birthplace` 模板 | 同上 |
| `Readme` | 2017 Day of the Devs 试玩版说明 | 无关 |

> 游戏中实际使用的是 `FateBaseIds`（`gunned-killer` 一代）配合 `Lang` 的 `fate_parts_*` / `fate_ent_*` 键。**不要基于上面这四张表建任何逻辑。**

## 9. `bookPageId` 全集（来自 `css/Assembly-CSharp/BookSpec.cs`）

**静态页**（`BookSpec` 构造函数逐个 `AddPage`）：

```
title  preface  toc  maps  crew  glossary  last
air  desk  cover  folio-chart  folio-deck  folio-sketch
scrollable-manifest  screenplay  message
```

**随章节/时刻动态生成**（`BookSpec.cs:132-144`）：

| 形式 | 例子 | 触发条件 |
|---|---|---|
| `<disasterId>` | `d000` | 每章一个 Chapter 页 |
| `<moment.id>` | `d000-stow-m00-seag` | 每个 Death 页（`MomentLogic` 会写入它） |
| `<disasterId>-disappear` | `d030-disappear` | 该章有失踪者时 |
| `<disasterId>-disappear2` | `d060-disappear2` | 失踪者 > 4 人时（`numDisappearCrewPages == 2`） |

## 10. 相关脚本

| 脚本 | 作用 |
|---|---|
| `parse_assets.py` | 本文件的生成脚本 |
| `to_json.py` | 把 `txtAssetDump/` 转成整洁 JSON → `jsonDump/*.json` |
| `validate_ids.py` | 端到端验证（180 条 face） |
| `inspect_dump.py` | 预览 dump 里任意一张表 |

> 机器可读的逐表数据见 `jsonDump/`（每张表一个 JSON，文件名已去掉 `-resources.assets-NN`）。

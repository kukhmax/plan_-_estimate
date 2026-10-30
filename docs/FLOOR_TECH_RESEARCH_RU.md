# Технология пола: исследование и правила приложения (2026-10-30)

Запрос владельца: «Надо переделать технические основания для пола, также работы и фразы для заказчика. Для пола технология отличается от стен и потолков. Подготовка под плитку, микроцемент, ламинат, паркет и т. п. разные — всё это надо учесть».

**Статус: DRAFT.** Цифры собраны поиском по открытым источникам (карты производителей, инструкции, спецификации, отраслевые статьи). Страницы источников не открывались целиком: сеть сессии не пускает на большинство сайтов, а тексты норм (PN-EN, ITB) платные. Все записи базы знаний — DRAFT с пометкой UNVERIFIED. Пороги — справочные данные: их можно поменять новой версией правила без переделки кода.

## Что было не так

Осмотр пола версии 1 (UX walk B4) писал те же ключи находок, что и стены (`HIGH_MOISTURE`, `CRACK`, `UNEVENNESS` …). Поэтому пол получал стеновые риски и вместе с ними:
- стеновые основания («Dopuszczalne odchylenia tynku» по PN-70/B-10100, «Włóknina szklana», «Wilgotność przed gładzią i malowaniem»);
- стеновые фразы и стеновые работы.

Кроме того, осмотр не спрашивал, **под какое покрытие** готовится пол, а от этого зависят допуски.

## Что сделано

1. **Осмотр пола версии 2** для всех пяти оснований пола: Jastrych, Beton, Stara płytka, Podłoga z desek, Inne. Новый раздел «Pod jaką okładzinę»:
   - покрытие: плитка, крупноформатная плитка, микроцемент, ламинат, паркет/доска, винил/LVT/ПВХ, «ещё неизвестно»;
   - мокрая зона;
   - тёплый пол.

   Все находки пола теперь свои (`FLOOR_*`). Измеренные числа тоже стали находками: влажность CM, ровность на 2 м, уровень. Добавлен вопрос «слабый верхний слой».

   Старые осмотры (версия 1) остаются как были. Новые начинаются с версии 2.
2. **40 правил риска пола** (`backend/app/domain/data/floor_rules.py`). Они читают только находки пола, поэтому стеновые риски на полу больше не появляются, и наоборот.
3. **14 работ пола в прайсе**, без цен (OWN_PRICE). Каждый риск пола рекомендует свою работу. Работы пола предлагаются только для пола.
4. **Фразы для заказчика**: по одной на каждый риск пола, на PL/RU/UK/EN.
5. **База знаний**: 15 источников и 15 записей «Podstawa techniczna» для пола, связанных с рисками.

## Пороги (что принято и откуда)

### Влажность основания (замер CM, %)

| Основание | Без тёплого пола | С тёплым полом | Источник |
|---|---|---|---|
| Цементная стяжка / бетон | > 2,0 % → риск (CRITICAL, блок) | > 1,8 % | PSP IT 1/1/2015; Janser (со ссылкой на ITB); Barlinek |
| Ангидритовая стяжка | > 0,5 % | > 0,3 % | Barlinek; карты производителей |
| Деревянное основание (доски, плиты) | > 12 % (влагомер для древесины) | — | Barlinek (гибридный пол) |

Разброс у производителей:
- для ламината Quick-Step и Pergo допускают < 2,5 % CM;
- для микроцемента карты систем допускают 3–4,5 %.

В приложении стоит общий, более строгий порог 2,0 %. Если хотите мягче для конкретного покрытия, это новая версия правила.

### Ровность (просвет под 2-метровым правилом, мм)

| Покрытие | Риск, если больше | Источник / комментарий |
|---|---|---|
| Керамическая плитка | 3 мм | Руководства и карты клеев: 2–3 мм; спецификация ST-2.6: основание под плитку 5 мм |
| Крупноформатная плитка | 2 мм | Руководства; инструкция Paradyż (полное опирание, клей S1/S2) |
| Микроцемент | 3 мм | Izolacje.com.pl (критерии приёмки) |
| Ламинат | 3 мм | Barlinek 3 мм / 2 м (или 2 мм / 1 м); Quick-Step 2 мм / 1 м и 1 мм / 20 см |
| Паркет / доска | 3 мм | Barlinek (доска); паркет на клей бывает строже — смотреть карту клея |
| Винил / LVT на клей | 2 мм | Viterra 2 мм / 1 м; другие инструкции до 2 мм / 1 м |
| Покрытие не выбрано | 5 мм | Спецификация ST-2.6 (основание) |
| Уровень по всему помещению | 5 мм | Спецификация ПГ (пол: 2 мм / 2 м по плоскости, 5 мм по горизонтали) |

### Прочее

- **Дилатации**:
  - периметральный шов (лента ~1 см);
  - поля стяжки: бетонная ~30 м², цементная ~40 м²; с тёплым полом шов обязателен при площади > 40 м² или стороне > 8 м;
  - швы также в дверных проёмах и в Г-образных помещениях; переносятся в покрытие (Murator).
- **Гидроизоляция в мокрой зоне** (Ceresit CL 51, Atlas Woder):
  - два слоя, лента в углах, на швах и у трапа;
  - CL 51 не для старой плитки;
  - вся мокрая зона пола + цоколь стен.
- **Плитка на плитку** (Ceresit):
  - простучать, слабую плитку снять;
  - обезжирить, нанести адгезионный грунт (и на швы);
  - клей C2, S1.
- **Микроцемент** (Weber):
  - механическая очистка;
  - эпоксидный грунт + сухой кварцевый песок 0,1–0,5 мм;
  - прочность на отрыв ≥ 1,5 Н/мм² (у других систем ≥ 1,0);
  - трещины — ламинат из стекломата на эпоксиде;
  - тёплый пол выключить за 48 ч.
- **Ламинат на минеральном основании** (SWISSKRONO, Quick-Step):
  - плёнка PE ≥ 0,2 мм внахлёст ~15 см, проклеить лентой;
  - зазор у стен 8–15 мм (по инструкции), не заполнять.
- **Доски под плитку** (Murator):
  - притянуть доски к лагам;
  - OSB/3 ~18 мм на жёсткие доски, ~25 мм на менее жёсткие;
  - отшлифовать, обеспылить, клей S1/S2.

## Риски пола и рекомендуемые работы

| Риск | Когда | Работа |
|---|---|---|
| FLOOR_MOISTURE_CEMENT / _HEATED | цемент/бетон, CM > 2,0 / 1,8 | Замер CM |
| FLOOR_MOISTURE_ANHYDRITE / _HEATED | ангидрит, CM > 0,5 / 0,3 | Замер CM |
| FLOOR_MOISTURE_SUSPECTED | признаки влаги, замера нет | Замер CM |
| FLOOR_WOOD_MOISTURE | доски, > 12 % | — |
| FLOOR_FLATNESS_TILES / _LARGE_TILES / _MICROCEMENT / _LAMINATE / _WOOD / _VINYL / _GENERAL | ровность выше порога покрытия | Самовыравнивающаяся смесь |
| FLOOR_LEVEL_OUT | уровень > 5 мм | Самовыравнивающаяся смесь |
| FLOOR_CRACK_REPAIR | трещины (кроме микроцемента) | «Сшивание» трещин |
| FLOOR_CRACK_MICROCEMENT | трещины под микроцемент (блок) | Сшивание + эпоксидный грунт |
| FLOOR_SCREED_HOLLOW | глухой звук стяжки (блок) | Ремонт отслоившейся стяжки |
| FLOOR_SURFACE_WEAK | слабый верх (кроме ламината, блок) | Шлифовка + грунт |
| FLOOR_SURFACE_LOOSE / _DUSTY / _OILY | рыхлое / пыль / жир | Шлифовка / грунт / шлифовка |
| FLOOR_EXPANSION_JOINTS / _HEATED | нет швов (без / с тёплым полом) | Деформационный шов |
| FLOOR_OLD_TILES_HOLLOW / _BOND / _LAYERS | старая плитка: глухая / глазурь / 2 слоя | Демонтаж / адгезионный грунт / демонтаж |
| FLOOR_BOARDS_FLEX | доски гуляют (блок) | Крепление досок к лагам |
| FLOOR_WOOD_DECAY | гниль, жучок (блок) | — (решение о замене) |
| FLOOR_BOARDS_UNDER_TILES / _LARGE_TILES / _MICROCEMENT | доски под жёсткое покрытие | OSB / фанера |
| FLOOR_WET_ZONE_TILES / _LARGE_TILES / _MICROCEMENT | мокрая зона | Гидроизоляция под плитку |
| FLOOR_WET_ZONE_LAMINATE / _WOOD | ламинат / дерево в мокрой зоне | — (решение клиента, протокол) |
| FLOOR_LAMINATE_VAPOUR | ламинат на минеральном основании | Плёнка PE |
| FLOOR_MICROCEMENT_PREP | микроцемент | Эпоксидный грунт с песком |
| FLOOR_LARGE_TILES_BED | крупноформатная плитка | — (метод укладки) |
| FLOOR_VINYL_SMOOTHING | винил на клей по минеральному основанию | Грунт + выравнивающая смесь |

## Что нужно от владельца

1. Проверить пороги (особенно плитку 3 мм и общий 2,0 % CM под микроцемент) и принять их или назвать свои.
2. Задать цены 14 работ пола в «Cennik»: они добавляются без цены.
3. Отметить источники, которые вы признаёте (записи станут APPROVED только с датой проверки).

## Источники

- [PSP — Wymagania dla podkładów (jastrychów) cementowych, IT 1/1/2015](https://www.posadzkarze.com.pl/files/Informacje_Techniczne_pdf/156918541/lib/IT_1_1_2015_Wymagania_dla_podk%C5%82adow_(jastrychow)_cementowych_zaktualizowana_06_2023.pdf)
- [Janser — pomiar wilgotności podkładu](https://janser.pl/porady-techniczne/pomiar-wilgotnosci-podkladu/)
- [Barlinek — warunki użytkowania podłogi hybrydowej](https://www.barlinek.com.pl/wp-content/uploads/2025/02/warunki-uzytkowania-i-pielegnacji-podlogi-hybrydowej.pdf)
- [Barlinek — podłogi na systemach ogrzewania podłogowego](https://www.barlinek.com.pl/wp-content/uploads/2025/02/podlogi-barlinka-na-systemach-ogrzewania-i-chlodzenia-podlogowego.pdf)
- [Quick-Step — instrukcja montażu laminatu](https://api-bw.vox.pl/file/product/instruction/Instrukcja-montażu-Quick-Step-laminat---LMP.pdf)
- [SWISSKRONO — zasady montażu paneli](https://static01.leroymerlin.pl/files/product/attachment/389/14389/SWISSKRONO_Zasady%20monta%C5%BCu%20i%20u%C5%BCytkowania%20paneli%20pod%C5%82ogowych%20oraz%20gwarancja.pdf)
- [Viterra — instrukcja montażu winylu](https://api-bw.vox.pl/file/product/instruction/2019.06.14-Viterra-Instrukcja-montazu-PL.pdf)
- [ST-2.6 — specyfikacja techniczna (BIP Małopolska)](https://bip.malopolska.pl/pobierz/420147.html)
- [SST posadzki — Politechnika Gdańska](https://dzp.pg.edu.pl/data/005741216817039.pdf)
- [Paradyż — instrukcja montażu płyt wielkoformatowych](https://www.paradyz.com/Pliki_do_pobrania/Instrukcje/Instrukcja-montazu-plyt-wielkoformatowych-21-04-2021.pdf)
- [Ceresit CL 51 — karta techniczna](https://datasheets.tdx.henkel.com/CERESIT-CL-51-pl_PL.pdf)
- [Atlas Woder — karta techniczna](https://www.atlas.com.pl/wp-content/uploads/2026/08/55aa0aa1809637f4dcb8cd2c5284cae5992a6a83_pl_1891_20230926_151558.pdf)
- [Ceresit — nowe płytki na stare płytki](https://www.ceresit.pl/pl/practices/tiling/nowe-p_ytki-na-stare-pytki.html)
- [Weber — mikrocement na podłodze](https://www.pl.weber/systemy-podlogowe/posadzki-i-powloki-dekoracyjne/mikrocement-na-podlodze-jak-wykonac-posadzka-z-mikrocementu)
- [Izolacje — kryteria odbiorowe posadzek z mikrocementu](https://www.izolacje.com.pl/artykul/posadzki-podlogi/287606,kryteria-odbiorowe-posadzek-z-mikrocementu)
- [Murator — dylatacja posadzki](https://muratordom.pl/wnetrza/prace-wykonczeniowe/dylatacja-posadzki-jak-zrobic-szczeliny-dylatacyjne-aa-v6co-rcUg-imyQ.html)
- [Murator — wymiana parkietu na płytki (OSB na deskach)](https://muratordom.pl/remont-domu/odnawianie-wnetrz/wymiana-parkietu-na-plytki-gresowe-jak-to-prawidlowo-zrobic-aa-WyX8-8G8Q-2Fh6.html)
- [Inspekcja Domu — odbiór mieszkania, odchyłki](https://www.inspekcjadomu.pl/porady/odbior-mieszkania-normy-i-odchylki/)

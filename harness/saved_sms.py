"""Hindi and Chinese for the saved English SMS on the landing cards.

David's offer file already has English and Spanish. This does not edit that file.
Dollar amounts, plan names, and the YES/STOP reply words stay as in the English.
"""

from __future__ import annotations

import re

_MONEY = r"\$[0-9][0-9,]*(?:\.[0-9]+)?"
_GREET = "Hi there. "
_STOP = " Reply STOP to opt out."


def hindi_and_chinese(english: str | None) -> tuple[str, str]:
    """Return (Hindi, Simplified Chinese) for one saved English draft. Blank stays blank."""
    text = "" if english is None else str(english).strip()
    if not text or text.lower() == "nan":
        return "", ""
    if not text.startswith(_GREET) or not text.endswith(_STOP):
        raise ValueError(f"saved SMS is not the expected shape: {text[:80]}")
    body = text[len(_GREET) : -len(_STOP)]
    hindi, chinese = _body(body)
    return f"नमस्ते। {hindi} संदेश बंद करने के लिए STOP लिखकर जवाब दें।", f"您好。{chinese}回复 STOP 即可退订。"


def _body(body: str) -> tuple[str, str]:
    for pattern, builder in _PATTERNS:
        match = pattern.fullmatch(body)
        if match:
            return builder(match)
    raise ValueError(f"no Hindi/Chinese pattern for: {body[:160]}")


def _why(text: str) -> tuple[str, str]:
    patterns: list[tuple[re.Pattern[str], object]] = [
        (
            re.compile(r"Your promo ended and your bill went up (\d+)%"),
            lambda m: (
                f"आपकी प्रोमो खत्म हो गई और बिल {m.group(1)}% बढ़ गया",
                f"您的优惠已经结束，账单上涨了{m.group(1)}%",
            ),
        ),
        (
            re.compile(r"Your bill went up (\d+)%"),
            lambda m: (f"आपका बिल {m.group(1)}% बढ़ गया", f"您的账单上涨了{m.group(1)}%"),
        ),
        (
            re.compile(r"You've reported (\d+) network issues? lately"),
            lambda m: (
                f"आपने हाल ही में {m.group(1)} नेटवर्क समस्याएँ बताई हैं",
                f"您最近报告了{m.group(1)}次网络问题",
            ),
        ),
        (
            re.compile(r"You have (\d+) support requests? we haven't resolved yet"),
            lambda m: (
                f"आपके {m.group(1)} सहायता अनुरोध अभी हल नहीं हुए हैं",
                f"您有{m.group(1)}个客服请求我们还没有解决",
            ),
        ),
        (
            re.compile(r"You're using about (\d+) GB a month on a plan with (\d+) GB of premium data"),
            lambda m: (
                f"आप महीने में लगभग {m.group(1)} GB इस्तेमाल कर रहे हैं, और प्लान में {m.group(2)} GB प्रीमियम डेटा है",
                f"您每月大约使用{m.group(1)} GB，套餐包含{m.group(2)} GB优质流量",
            ),
        ),
        (
            re.compile(r"Your data use is up (\d+)% over the past year"),
            lambda m: (
                f"पिछले साल की तुलना में आपका डेटा उपयोग {m.group(1)}% बढ़ा है",
                f"过去一年您的流量使用增加了{m.group(1)}%",
            ),
        ),
        (
            re.compile(r"You use about (\d+) GB of hotspot a month and your plan has no high-speed hotspot"),
            lambda m: (
                f"आप महीने में लगभग {m.group(1)} GB हॉटस्पॉट इस्तेमाल करते हैं, और प्लान में हाई-स्पीड हॉटस्पॉट नहीं है",
                f"您每月大约使用{m.group(1)} GB热点，而套餐没有高速热点",
            ),
        ),
        (
            re.compile(r"Your phone is about (\d+) years old"),
            lambda m: (f"आपका फ़ोन लगभग {m.group(1)} साल पुराना है", f"您的手机大约已使用{m.group(1)}年"),
        ),
        (
            re.compile(r"We want to make sure your plan still fits you"),
            lambda _m: (
                "हम यह पक्का करना चाहते हैं कि प्लान अब भी आपके लिए सही है",
                "我们想确认套餐仍然适合您",
            ),
        ),
    ]
    for pattern, builder in patterns:
        match = pattern.fullmatch(text)
        if match:
            return builder(match)
    raise ValueError(f"no translation for the reason: {text}")


def _perk(text: str) -> tuple[str, str]:
    if text == "unlimited premium data":
        return "असीमित प्रीमियम डेटा", "无限优质流量"
    if text == "room to add more lines":
        return "और लाइनें जोड़ने की जगह", "添加更多线路的空间"
    if text == "more room to grow":
        return "बढ़ने के लिए और जगह", "更多扩展空间"
    match = re.fullmatch(r"(\d+(?:\.\d+)?) GB of high-speed hotspot", text)
    if match:
        amount = match.group(1)
        return f"{amount} GB हाई-स्पीड हॉटस्पॉट", f"{amount} GB高速热点"
    match = re.fullmatch(r"(\d+) GB of premium data per line", text)
    if match:
        amount = match.group(1)
        return f"प्रति लाइन {amount} GB प्रीमियम डेटा", f"每条线路{amount} GB优质流量"
    raise ValueError(f"no translation for the benefit: {text}")


def _calm(text: str) -> tuple[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("Prefer to keep your plan"):
        return "अपना प्लान रखना चाहते हैं? कुछ करने की ज़रूरत नहीं।", "想保留现有套餐？不必做任何事。"
    if cleaned.startswith("Happy as is"):
        return "जैसे है, वैसे ही ठीक है? कुछ करने की ज़रूरत नहीं।", "维持现状就可以？不必做任何事。"
    if cleaned.startswith("No need"):
        return "कुछ करने की ज़रूरत नहीं।", "不必做任何事。"
    raise ValueError(f"no translation for the aside: {text}")


def _giveup(item: str) -> tuple[str, str]:
    if item == "high-speed hotspot":
        return "हाई-स्पीड हॉटस्पॉट", "高速热点"
    if item == "watch/tablet lines":
        return "वॉच/टैबलेट लाइनें", "手表/平板线路"
    if item == "some streaming perks":
        return "कुछ स्ट्रीमिंग लाभ", "部分流媒体权益"
    match = re.fullmatch(r"the (\d+)-Year Price Guarantee", item)
    if match:
        years = match.group(1)
        return f"{years} साल की कीमत गारंटी", f"{years}年价格保障"
    match = re.fullmatch(r"more than (\d+) lines", item)
    if match:
        count = match.group(1)
        return f"{count} से ज़्यादा लाइनें", f"超过{count}条线路"
    match = re.fullmatch(r"hotspot drops from (\d+(?:\.\d+)?) GB to (\d+(?:\.\d+)?) GB", item)
    if match:
        left, right = match.group(1), match.group(2)
        return f"हॉटस्पॉट {left} GB से {right} GB हो जाता है", f"热点从{left} GB降到{right} GB"
    raise ValueError(f"no translation for the tradeoff: {item}")


def _giveups(text: str | None) -> tuple[str, str]:
    if not text:
        return "", ""
    hindi, chinese = [], []
    for item in text.split(", "):
        one_hi, one_zh = _giveup(item)
        hindi.append(one_hi)
        chinese.append(one_zh)
    return "आप छोड़ेंगे: " + ", ".join(hindi) + "। ", "您会失去：" + "、".join(chinese) + "。"


def _rule(text: str | None) -> tuple[str, str]:
    if not text:
        return "", ""
    match = re.fullmatch(r"(\d+) or more lines", text)
    if match:
        count = match.group(1)
        return f" ({count} या अधिक लाइनें)", f"（{count}条或更多线路）"
    match = re.fullmatch(r"(\d+) to (\d+) lines", text)
    if match:
        return f" ({match.group(1)} से {match.group(2)} लाइनें)", f"（{match.group(1)}至{match.group(2)}条线路）"
    raise ValueError(f"no translation for the line rule: {text}")


def _enough(match: re.Match[str]) -> tuple[str, str]:
    if match.group("enough"):
        return ", आपके उपयोग के लिए पर्याप्त", "，足够您使用"
    return "", ""


_PATTERNS: list[tuple[re.Pattern[str], object]] = []


def _add(pattern: str, builder) -> None:
    _PATTERNS.append((re.compile(pattern), builder))


_add(
    rf"(?P<why>.+)\. We want to get this fixed: reply YES and a specialist will call you\.",
    lambda m: (
        (lambda pair: (
            f"{pair[0]}। हम इसे ठीक कराना चाहते हैं: YES लिखकर जवाब दें और एक विशेषज्ञ आपको कॉल करेगा।",
            f"{pair[1]}。我们想把这个问题解决：回复 YES，专员会给您打电话。",
        ))(_why(m.group("why")))
    ),
)
_add(
    rf"(?P<why>.+)\. A specialist will call you to fix it, and we'll add a one-time (?P<amt>{_MONEY}) credit to your next bill\. Reply YES to schedule the call\.",
    lambda m: (
        (lambda pair: (
            f"{pair[0]}। एक विशेषज्ञ इसे ठीक करने के लिए कॉल करेगा, और हम आपके अगले बिल में एक बार का {m.group('amt')} क्रेडिट जोड़ेंगे। कॉल तय करने के लिए YES लिखकर जवाब दें।",
            f"{pair[1]}。专员会打电话为您解决，我们还会在下一期账单加入一次性{m.group('amt')}信用金。回复 YES 预约通话。",
        ))(_why(m.group("why")))
    ),
)
_add(
    rf"(?P<why>.+)\. We'd like to give you a one-time (?P<amt>{_MONEY}) credit on your next bill\. Reply YES to accept\.",
    lambda m: (
        (lambda pair: (
            f"{pair[0]}। हम आपके अगले बिल पर एक बार का {m.group('amt')} क्रेडिट देना चाहते हैं। स्वीकार करने के लिए YES लिखकर जवाब दें।",
            f"{pair[1]}。我们想在您的下一期账单给予一次性{m.group('amt')}信用金。回复 YES 即可接受。",
        ))(_why(m.group("why")))
    ),
)
_add(
    rf"You could pay (?P<amt>{_MONEY})/month less: (?P<plan>.+?) has (?P<benefit>unlimited premium data|\d+ GB of premium data per line)(?P<enough>, enough for your use)?\. (?:You'd give up: (?P<give>.+?)\. )?Reply YES to move, or ignore this to keep your plan\.",
    lambda m: (
        (lambda benefit, enough, give: (
            f"आप हर महीने {m.group('amt')} कम दे सकते हैं: {m.group('plan')} में {benefit[0]}{enough[0]} है। {give[0]}बदलने के लिए YES लिखकर जवाब दें, या प्लान रखने के लिए इस संदेश को छोड़ दें।",
            f"您每月可以少付{m.group('amt')}：{m.group('plan')}包含{benefit[1]}{enough[1]}。{give[1]}回复 YES 即可更换，或不理此消息以保留套餐。",
        ))(_perk(m.group("benefit")), _enough(m), _giveups(m.group("give")))
    ),
)
_add(
    r"(?:Thanks for (?P<years>\d+) years! |Thanks for being with us! )?(?:Your (?P<plan>.+?) has a (?P<gyear>\d+)-Year Price Guarantee\. |Your (?P<plan2>.+?) includes (?P<benefit>unlimited premium data|\d+ GB of premium data per line)\. )?Anything not working\? Reply YES for a free plan review\.",
    lambda m: _check_in(m),
)
_add(
    rf"Good news: your (?P<count>\d+) lines qualify for (?:our )?(?P<plan>.+?)(?: \((?P<rule>[^)]+)\))?\. Same features, (?P<new>{_MONEY})/month instead of (?P<old>{_MONEY})\. Nothing else changes\. Reply YES and we'll move you\.",
    lambda m: (
        (lambda rule: (
            f"अच्छी खबर: आपकी {m.group('count')} लाइनें {m.group('plan')}{rule[0]} के लिए योग्य हैं। वही सुविधाएँ, {m.group('old')} के बजाय {m.group('new')} प्रति माह। और कुछ नहीं बदलता। YES लिखकर जवाब दें और हम आपको बदल देंगे।",
            f"好消息：您的{m.group('count')}条线路符合{m.group('plan')}{rule[1]}。功能相同，每月{m.group('new')}，而不是{m.group('old')}。其他都不变。回复 YES，我们为您更换。",
        ))(_rule(m.group("rule")))
    ),
)
_add(
    rf"Good news: your line qualifies for (?:our )?(?P<plan>.+?)(?: \((?P<rule>[^)]+)\))?\. Same features, (?P<new>{_MONEY})/month instead of (?P<old>{_MONEY})\. Nothing else changes\. Reply YES and we'll move you\.",
    lambda m: (
        (lambda rule: (
            f"अच्छी खबर: आपकी लाइन {m.group('plan')}{rule[0]} के लिए योग्य है। वही सुविधाएँ, {m.group('old')} के बजाय {m.group('new')} प्रति माह। और कुछ नहीं बदलता। YES लिखकर जवाब दें और हम आपको बदल देंगे।",
            f"好消息：您的线路符合{m.group('plan')}{rule[1]}。功能相同，每月{m.group('new')}，而不是{m.group('old')}。其他都不变。回复 YES，我们为您更换。",
        ))(_rule(m.group("rule")))
    ),
)
_add(
    rf"(?P<why>.+?)\. (?P<plan>.+?) gives every line unlimited premium data for (?P<amt>{_MONEY})/month more for your (?P<count>\d+) lines\.(?P<calm> Prefer to keep your plan\? No need to do anything\.| Happy as is\? No need to do anything\.| No need to do anything\.) Reply YES to compare plans\.",
    lambda m: (
        (lambda why, calm: (
            f"{why[0]}। {m.group('plan')} आपकी {m.group('count')} लाइनों के लिए हर लाइन पर असीमित प्रीमियम डेटा देता है, हर महीने {m.group('amt')} अधिक में। {calm[0]} प्लान की तुलना के लिए YES लिखकर जवाब दें।",
            f"{why[1]}。{m.group('plan')}为您的{m.group('count')}条线路提供每条线路无限优质流量，每月多{m.group('amt')}。{calm[1]}回复 YES 比较套餐。",
        ))(_why(m.group("why")), _calm(m.group("calm")))
    ),
)
_add(
    rf"(?P<why>.+?)\. (?P<plan>.+?) gives you (?P<perk>.+?) for (?P<amt>{_MONEY})/month more\.(?P<calm> Prefer to keep your plan\? No need to do anything\.| Happy as is\? No need to do anything\.| No need to do anything\.) Reply YES to compare plans\.",
    lambda m: (
        (lambda why, perk, calm: (
            f"{why[0]}। {m.group('plan')} आपको {perk[0]} देता है, हर महीने {m.group('amt')} अधिक में। {calm[0]} प्लान की तुलना के लिए YES लिखकर जवाब दें।",
            f"{why[1]}。{m.group('plan')}为您提供{perk[1]}，每月多{m.group('amt')}。{calm[1]}回复 YES 比较套餐。",
        ))(_why(m.group("why")), _perk(m.group("perk")), _calm(m.group("calm")))
    ),
)
_add(
    rf"Your bill went up because a promo credit ended, not because your plan price changed\. (?P<plan>.+?) talk, text and data stay covered by your (?P<years>\d+)-Year Price Guarantee\. We'll add a one-time (?P<care>{_MONEY}) credit(?: and (?P<loy>{_MONEY})/month off)?\. Reply YES to accept\.",
    lambda m: _bill_shock(m),
)
_add(
    rf"You can add Home Internet from (?P<start>{_MONEY})/month and get (?P<off>{_MONEY})/month off with your phone lines\.(?P<calm> Happy as is\? No need to do anything\.| No need to do anything\.) Reply YES for details\.",
    lambda m: (
        (lambda calm: (
            f"आप फ़ोन लाइनों के साथ Home Internet {m.group('start')} प्रति माह से जोड़ सकते हैं, और {m.group('off')} प्रति माह की छूट पा सकते हैं। {calm[0]} विवरण के लिए YES लिखकर जवाब दें।",
            f"您可以每月{m.group('start')}起添加 Home Internet，并随手机线路每月减免{m.group('off')}。{calm[1]}回复 YES 了解详情。",
        ))(_calm(m.group("calm")))
    ),
)
_add(
    rf"Thanks for (?P<years>\d+) years with us\. You can get a (?P<amt>{_MONEY})/month loyalty credit\. Reply YES to add it\.",
    lambda m: (
        f"हमारे साथ {m.group('years')} सालों के लिए धन्यवाद। आप {m.group('amt')} प्रति माह का लॉयल्टी क्रेडिट ले सकते हैं। जोड़ने के लिए YES लिखकर जवाब दें।",
        f"感谢您与我们相伴{m.group('years')}年。您可以获得每月{m.group('amt')}的忠诚信用金。回复 YES 即可添加。",
    ),
)
_add(
    rf"Your plan is our (?P<cur>.+)\. (?P<nxt>.+) lets you add lines later, for (?P<amt>{_MONEY})/month more\. Reply YES to learn more\.",
    lambda m: (
        f"आपका प्लान हमारा {m.group('cur')} है। {m.group('nxt')} बाद में लाइनें जोड़ने देता है, हर महीने {m.group('amt')} अधिक में। और जानने के लिए YES लिखकर जवाब दें।",
        f"您的套餐是我们的{m.group('cur')}。{m.group('nxt')}以后可以加线路，每月多{m.group('amt')}。回复 YES 了解更多。",
    ),
)
_add(
    rf"(?P<why>.+)\. Trade it in and get (?P<amt>{_MONEY}) in bill credits over (?P<months>\d+) months toward a new phone\.(?P<calm> Prefer to keep your plan\? No need to do anything\.| Happy as is\? No need to do anything\.| No need to do anything\.) Reply YES to see phones\.",
    lambda m: (
        (lambda why, calm: (
            f"{why[0]}। इसे ट्रेड-इन करें और नए फ़ोन के लिए {m.group('months')} महीनों में बिल क्रेडिट के रूप में {m.group('amt')} पाएँ। {calm[0]} फ़ोन देखने के लिए YES लिखकर जवाब दें।",
            f"{why[1]}。以旧换新，可在{m.group('months')}个月内获得{m.group('amt')}账单信用金，用于新手机。{calm[1]}回复 YES 查看手机。",
        ))(_why(m.group("why")), _calm(m.group("calm")))
    ),
)
_add(
    r"Your (?P<plan>.+) already includes a streaming video service with ads at no extra cost\. Reply YES and we'll help you set it up\.",
    lambda m: (
        f"आपके {m.group('plan')} में विज्ञापनों वाली स्ट्रीमिंग वीडियो सेवा पहले से शामिल है, बिना अतिरिक्त कीमत के। YES लिखकर जवाब दें और हम इसे चालू करने में मदद करेंगे।",
        f"您的{m.group('plan')}已包含带广告的流媒体视频服务，无需额外费用。回复 YES，我们帮您开通。",
    ),
)


def _check_in(match: re.Match[str]) -> tuple[str, str]:
    if match.group("years"):
        thanks_hi = f"{match.group('years')} सालों के लिए धन्यवाद! "
        thanks_zh = f"感谢您{match.group('years')}年来的相伴！"
    elif match.group(0).startswith("Thanks for being with us"):
        thanks_hi = "हमारे साथ रहने के लिए धन्यवाद! "
        thanks_zh = "感谢您与我们相伴！"
    else:
        thanks_hi = thanks_zh = ""
    if match.group("plan"):
        fact_hi = f"आपके {match.group('plan')} पर {match.group('gyear')} साल की कीमत गारंटी है। "
        fact_zh = f"您的{match.group('plan')}有{match.group('gyear')}年价格保障。"
    elif match.group("plan2"):
        benefit = _perk(match.group("benefit"))
        fact_hi = f"आपके {match.group('plan2')} में {benefit[0]} शामिल है। "
        fact_zh = f"您的{match.group('plan2')}包含{benefit[1]}。"
    else:
        fact_hi = fact_zh = ""
    ask_hi = "कुछ काम नहीं कर रहा? मुफ़्त प्लान समीक्षा के लिए YES लिखकर जवाब दें।"
    ask_zh = "有什么不正常吗？回复 YES 免费复查套餐。"
    return f"{thanks_hi}{fact_hi}{ask_hi}", f"{thanks_zh}{fact_zh}{ask_zh}"


def _bill_shock(match: re.Match[str]) -> tuple[str, str]:
    loyalty = ""
    loyalty_zh = ""
    if match.group("loy"):
        loyalty = f" और हर महीने {match.group('loy')} कम"
        loyalty_zh = f"，并每月减免{match.group('loy')}"
    hindi = (
        f"बिल इसलिए बढ़ा क्योंकि एक प्रोमो क्रेडिट खत्म हुआ, प्लान की कीमत बदली नहीं। "
        f"आपके {match.group('plan')} पर कॉल, मैसेज और डेटा {match.group('years')} साल की कीमत गारंटी में रहते हैं। "
        f"हम एक बार का {match.group('care')} क्रेडिट जोड़ेंगे{loyalty}। स्वीकार करने के लिए YES लिखकर जवाब दें।"
    )
    chinese = (
        f"账单上涨是因为一项优惠信用金结束了，不是因为套餐价格变了。"
        f"您的{match.group('plan')}的通话、短信和流量仍在{match.group('years')}年价格保障之内。"
        f"我们将加入一次性{match.group('care')}信用金{loyalty_zh}。回复 YES 即可接受。"
    )
    return hindi, chinese

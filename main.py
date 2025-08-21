"""Entry point for the news-mvp project."""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.classifier import classify_news
from src.prioritizer import adjust_priority
from src.summarizer import summarize_news
from src.user_profile import get_user_profile


def main() -> None:
    """Run the news summarizer/classifier with a sample input."""

    user = get_user_profile("test_user")

    news_samples = [
        # 1 — Экономика
        """The U.S. stock market is hovering at record highs, but economists such as Bob Elliott
        (Unlimited Funds) and Tiffany Wilding (PIMCO) warn that under the surface, weaknesses are growing.
        Consumer spending is slowing, job growth is weakening, and reduced immigration is creating
        structural imbalances hidden by market optimism. The minutes of the Fed’s July meeting revealed
        concerns about tariffs and cooling demand. While investors still expect rate cuts, confidence is
        fragile. The bond market shows weaker dynamics compared to equities. The S&P 500 gained 3.1% in
        the quarter and 8.7% year-to-date, but largely thanks to a few mega-cap tech stocks, raising fears
        of “structural fragility.” Wilding stresses that current policy may only deepen the disconnect
        between financial markets and the real economy. Analysts note the eerie parallels with the early
        2000s tech bubble and the mid-2000s housing bubble, where confidence in growth masked deepening
        weaknesses. This time, the concern is that AI-led investments create both extraordinary
        concentration risk and dependency on fragile narratives about productivity that are not yet
        supported by broad-based data. If the narrow rally falters, spillover effects could cascade into
        credit markets, consumer confidence, and global trade.""",
        # 2 — Спорт
        """Marcus Rashford bluntly describes Manchester United as stuck in “no man's land,” citing the
        relentless carousel of managers and strategies. He contrasts this with Liverpool's transformation
        under Jürgen Klopp, whose vision unified player development from academy to first team. United,
        Rashford argues, lacks consistency: sometimes the style is attacking, sometimes it is defensive,
        sometimes managers come and go and change everything—staff, diet, youth system, even medical teams.
        The results? Fifteenth place last season. Cup wins but no stability. Expensive signings—some useful,
        some not—arrive and leave quickly. The stadium is modernized, yet fans chant “no direction.” 
        United are, Rashford says, not failing but also not succeeding, trapped in cycles: optimism,
        disappointment, restart, optimism again, disappointment again. He adds, ‘Look at Liverpool:
        stability. Look at City: stability. At United? Churn. Too much churn.’ """,
        # 3 — Технологии
        """Databricks secures a colossal $10 billion funding round, boosting its valuation to $62 billion
        and highlighting the voracious investor interest in AI. Led by Thrive Capital with backing from
        heavyweights like Andreessen Horowitz, DST Global, GIC, and Insight Partners, the round will
        enable stock liquidity for employees, accelerate AI product development, and support acquisitive
        growth. With a $3 billion revenue run rate projected by January and an imminent shift to
        profitability, Databricks is positioning itself for the long game—far beyond typical
        liquidity-driven IPO timelines. Investors view it as a future platform leader in AI, prioritizing
        scale over speed. Executives argue that the company’s competitive moat is not only its data
        management tools but also its partnerships with the biggest cloud players, enabling deep
        integration into enterprise workloads. Analysts warn, however, that competition from OpenAI,
        Anthropic, and Google DeepMind will require continuous innovation and heavy spending.""",
        # 4 — Политика
        """In Washington, lawmakers clash—again—over federal budget priorities. The debate is messy,
        fragmented, filled with contradictions: some call for defense spending increases, others demand
        urgent cuts to balance the deficit, while still others mix these stances in strange ways. One
        senator declared, “We cannot both raise spending and cut taxes, but we must do both, somehow,
        for the people.” This confusing rhetoric echoes across cable news: some experts say the U.S. is
        at risk of a debt spiral, others say the debt is manageable, others dismiss the entire conversation.
        Public reaction is polarized: some fear inflation, some fear unemployment, some fear foreign
        competition. The White House insists compromise is possible but offers no plan. Meanwhile,
        lobbyists push for climate credits, defense contractors push for jets, states push for grants.
        Nothing is clear, nothing is stable. Analysts describe the process as “a fog of words,” and the
        result—gridlock—seems inevitable. Observers note the eerie similarity to the 2011 debt ceiling
        standoff, but this time with even less clarity, more talking points, less listening.""",
        # 5 — Климат
        """Severe floods hit Bangladesh, leaving thousands displaced, with humanitarian agencies warning
        that the disaster may worsen in coming weeks. Monsoon rains exceeded seasonal averages by nearly
        40%, overwhelming riverbanks and destroying vital infrastructure such as roads, bridges, and
        water-treatment facilities. Entire districts are under water, with agriculture severely damaged.
        Rice paddies and fisheries, critical to the livelihoods of millions, face long-term collapse.
        International aid has been slow to mobilize, in part due to strained global supply chains and
        competing crises in other regions. Climate scientists argue that such extreme weather events are
        increasingly linked to global warming and rising sea levels, warning that South Asia is among the
        most vulnerable areas in the world. Aid organizations stress the need for coordinated relief:
        shelter, medicine, food, and long-term resilience planning. The government pledges assistance but
        faces criticism for weak infrastructure spending and lack of preparedness.""",
        """Borussia Dortmund produced a stunning comeback to defeat Bayern Munich 3-2 in a dramatic Bundesliga clash. Bayern led 2-0 at halftime with goals from Kane and Musiala, but Dortmund responded with three unanswered goals in the second half. The decisive strike came from teenager Youssoufa Moukoko in stoppage time, sending Signal Iduna Park into euphoria. The victory narrows Bayern’s lead at the top of the Bundesliga to just one point.""",
        """In a thrilling NBA Finals Game 7, the Miami Heat edged out the Los Angeles Lakers 112-110 to clinch the championship. Jimmy Butler scored 35 points, including the game-winning free throws with just seconds left. LeBron James had a triple-double for the Lakers but missed a potential game-tying shot at the buzzer. The Heat’s victory marks their first championship since 2013 and solidifies Butler’s status as one of the league’s elite players.""",
    ]

    for news in news_samples:
        classification = classify_news(news, user_locale=user.locale)
        category = classification["category"]

        summary = summarize_news(news, category)
        final_priority = adjust_priority(classification, user)

        print("=" * 80)
        print(summary)
        print(f"Category: {classification['category']}")
        if classification["sports_subcategory"]:
            print(f"Sports subcategory: {classification['sports_subcategory']}")
        print(f"Confidence: {classification['confidence']:.2f}")
        print(f"Reasons: {classification['reasons']}")
        print(f"LLM priority: {classification['priority_llm']}")
        print(f"Final priority (adjusted for {user.user_id}): {final_priority}")


if __name__ == "__main__":
    main()

from schemas import AnalysisReport, Competitor, Recommendation, BusinessProfile


def demo_report(p: BusinessProfile) -> AnalysisReport:
    return AnalysisReport(
        summary=f"[DEMO DATA] {p.name} is priced mid-market in {p.neighborhood}; nearby shops win on speed.",
        competitors=[
            Competitor(name="Example Café A", price_range="$$", typical_wait="5-8 min", rating="4.5",
                       strengths=["fast service", "online ordering"],
                       customer_complaints=["limited seating"], source_urls=["https://example.com/a"]),
            Competitor(name="Example Café B", price_range="$$$", typical_wait="12-15 min", rating="4.2",
                       strengths=["unique menu"], customer_complaints=["long waits", "pricey"],
                       source_urls=["https://example.com/b"]),
        ],
        market_trends=["Customers favor shops with preorder/pickup", "Late-morning waits are the top complaint"],
        pricing_position="Roughly in line with the median of nearby competitors.",
        recommendations=[
            Recommendation(title="Add a pre-order option", area="wait_times", impact="high",
                           detail="Offer text/online pre-order for the morning rush.",
                           evidence="Competitor B's #1 complaint is wait time; Competitor A wins with online ordering."),
        ],
        caveats="Canned demo data, not real research.",
    )

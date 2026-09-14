from synergy_graph.v7_4_eurasian_qe import V74_NET_CANDIDATE_USD, simulate_packets


def main() -> None:
    print("EURASIAN QE / V7.4 ACCOUNTING SIMULATION")
    print(f"V7.4 net packet candidate: ${V74_NET_CANDIDATE_USD:.9f}")
    print("Starting system HardNAV: $1.00")
    print("External pool initial TVL: $118,000,000")
    print("Assumed fair ETH price: $2,500")
    print("External CPMM fee: 30 bps")
    print()

    for count in (1, 10, 100, 1_000, 10_000):
        pool, system, rows = simulate_packets(count)
        last = rows[-1]
        print(f"successful independently replenished packets: {count}")
        print(f"  consolidated system HardNAV: ${last.consolidated_system_hardnav_usd:,.6f}")
        print(f"  bridge reserve:             ${system.bridge_reserve:,.6f}")
        print(f"  insurance fund:             ${system.insurance_fund:,.6f}")
        print(f"  rebase fund:                ${system.rebase_fund:,.6f}")
        print(f"  owned external LP value:    ${last.system_external_lp_value_usd:,.6f}")
        print(f"  external pool TVL:          ${pool.fair_tvl:,.6f}")
        print(f"  external pool TVL gain:     ${pool.fair_tvl - 118_000_000:,.6f}")
        print(f"  last transient price lift:  {100 * last.transient_price_impact_fraction:.9f}%")
        print()

    print("IMPORTANT: repeated rows are a conditional scenario only.")
    print("The simulator does not assume the same arbitrage edge survives after execution.")
    print("Every repeated V7.4 packet must be independently discovered and proven profitable.")


if __name__ == "__main__":
    main()

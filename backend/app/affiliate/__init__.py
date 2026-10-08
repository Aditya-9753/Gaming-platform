"""Partner / affiliate platform.

Partners send traffic to the operator product (Rudra247) through tracking
links and earn CPA and/or revenue share on the players they bring. The chain:

    partner -> source -> tracking link -> click (click_id, first-party cookie)
    -> registration / deposit / daily revenue (signed S2S ingest)
    -> commission (CPA on qualified FTD, revshare on NGR)
    -> wallet ledger (pending -> available -> reserved) -> withdrawal

Money is ``Decimal`` (NUMERIC(19,4)) in USD everywhere in this package; the
wallet balances are a cache of the append-only ledger in
``aff_wallet_transactions`` and are only written by ``app.affiliate.ledger``.
"""

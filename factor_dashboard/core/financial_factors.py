"""财务类因子实现。

口径约定：
- 流量科目（利润表、现金流量表）先由年内累计值还原为单季，再滚动四季求和得到 TTM；
- 存量科目（资产负债表）取报告期末值；
- 所有财务数据按公告日对齐到交易日，避免使用未披露信息。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from . import indicators as ind
from .context import FactorContext

FINANCIAL_FACTORS: dict[str, Callable[[FactorContext], pd.DataFrame]] = {}


def factor(name: str):
    def decorator(func: Callable[[FactorContext], pd.DataFrame]):
        FINANCIAL_FACTORS[name] = func
        return func

    return decorator


# ---------------------------------------------------------------- 公共口径


def total_debt(ctx: FactorContext) -> pd.DataFrame:
    return (
        ctx.point("short_term_borrowings").fillna(0)
        + ctx.point("long_term_borrowings").fillna(0)
        + ctx.point("bonds_payable").fillna(0)
    )


def interest_free_current_liability(ctx: FactorContext) -> pd.DataFrame:
    components = [
        "notes_payable",
        "accounts_payable",
        "advance_receipts",
        "tax_payable",
        "interest_payable",
        "other_payables",
        "other_current_liabilities",
    ]
    return sum(ctx.point(name).fillna(0) for name in components)


def financial_assets(ctx: FactorContext) -> pd.DataFrame:
    components = ["cash", "financial_assets_trading", "notes_receivable", "available_for_sale"]
    return sum(ctx.point(name).fillna(0) for name in components)


def financial_liability(ctx: FactorContext) -> pd.DataFrame:
    interest_bearing = ctx.point("long_term_borrowings").fillna(0) + ctx.point(
        "bonds_payable"
    ).fillna(0)
    return (ctx.point("current_liabilities") - interest_free_current_liability(ctx)) + interest_bearing


def net_operating_assets(ctx: FactorContext) -> pd.DataFrame:
    operating_assets = ctx.point("total_assets") - financial_assets(ctx)
    operating_liability = ctx.point("total_liabilities") - financial_liability(ctx)
    return operating_assets - operating_liability


def market_leverage(ctx: FactorContext) -> pd.DataFrame:
    coupons = ctx.point("long_term_borrowings").fillna(0) + ctx.point("bonds_payable").fillna(0)
    return ind.safe_div(ctx.market_cap + coupons, ctx.market_cap)


def book_leverage(ctx: FactorContext) -> pd.DataFrame:
    coupons = ctx.point("long_term_borrowings").fillna(0) + ctx.point("bonds_payable").fillna(0)
    equity = ctx.point("equity_parent")
    return ind.safe_div(equity + coupons, equity)


def debt_to_asset(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("total_liabilities"), ctx.point("total_assets"))


def gross_margin_ttm(ctx: FactorContext, lag_q: int = 0) -> pd.DataFrame:
    revenue = ctx.ttm("revenue", lag_q)
    cost = ctx.ttm("cost", lag_q)
    return ind.safe_div(revenue - cost, revenue)


# ---------------------------------------------------------------- 盈利能力


@factor("net_profit_to_total_operate_revenue_ttm")
def net_profit_to_total_operate_revenue_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit"), ctx.ttm("total_revenue"))


@factor("net_profit_ratio")
def net_profit_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit"), ctx.ttm("revenue"))


@factor("operating_profit_ratio")
def operating_profit_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("operating_profit"), ctx.ttm("revenue"))


@factor("operating_profit_to_operating_revenue")
def operating_profit_to_operating_revenue(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("operating_profit"), ctx.ttm("total_revenue"))


@factor("gross_income_ratio")
def gross_income_ratio(ctx: FactorContext) -> pd.DataFrame:
    return gross_margin_ttm(ctx)


@factor("operating_cost_to_operating_revenue_ratio")
def operating_cost_to_operating_revenue_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cost"), ctx.ttm("revenue"))


@factor("profit_margin_ttm")
def profit_margin_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("operating_profit"), ctx.ttm("revenue"))


@factor("roa_ttm")
def roa_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit"), ctx.point("total_assets"))


@factor("ROAEBITTTM")
def roaebit_ttm(ctx: FactorContext) -> pd.DataFrame:
    numerator = ctx.ttm("total_profit") + ctx.ttm("interest_expense")
    return ind.safe_div(numerator, ctx.avg4("total_assets"))


@factor("roe_ttm")
def roe_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit"), ctx.point("total_equity"))


@factor("rnoa_ttm")
def rnoa_ttm(ctx: FactorContext) -> pd.DataFrame:
    return profit_margin_ttm(ctx) * asset_turnover_ttm(ctx)


@factor("roic_ttm")
def roic_ttm(ctx: FactorContext) -> pd.DataFrame:
    interest_bearing_noncurrent = ctx.point("long_term_borrowings").fillna(0) + ctx.point(
        "bonds_payable"
    ).fillna(0)
    invested = (
        ctx.point("total_equity")
        + ctx.point("total_liabilities")
        - interest_free_current_liability(ctx)
        - (ctx.point("non_current_liabilities") - interest_bearing_noncurrent)
    )
    return ind.safe_div(ctx.ttm("net_profit_parent"), ctx.avg4_frame(invested))


@factor("total_asset_turnover_rate")
def total_asset_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.point("total_assets"))


@factor("asset_turnover_ttm")
def asset_turnover_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.avg4_frame(net_operating_assets(ctx)))


@factor("current_asset_turnover_rate")
def current_asset_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.avg4("current_assets"))


@factor("fixed_assets_turnover_rate")
def fixed_assets_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.point("fixed_assets").fillna(0)
        + ctx.point("construction_in_progress").fillna(0)
        + ctx.point("construction_materials").fillna(0)
    )
    return ind.safe_div(ctx.ttm("revenue"), ctx.avg4_frame(base))


@factor("equity_turnover_rate")
def equity_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.point("total_equity"))


@factor("inventory_turnover_rate")
def inventory_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cost"), ctx.point("inventory"))


@factor("inventory_turnover_days")
def inventory_turnover_days(ctx: FactorContext) -> pd.DataFrame:
    return 360 / inventory_turnover_rate(ctx)


@factor("account_receivable_turnover_rate")
def account_receivable_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.avg4("accounts_receivable").fillna(0)
        + ctx.avg4("notes_receivable").fillna(0)
        + ctx.avg4("advance_receipts").fillna(0)
    )
    return ind.safe_div(ctx.ttm("revenue"), base)


@factor("account_receivable_turnover_days")
def account_receivable_turnover_days(ctx: FactorContext) -> pd.DataFrame:
    return 360 / account_receivable_turnover_rate(ctx)


@factor("accounts_payable_turnover_rate")
def accounts_payable_turnover_rate(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.avg4("accounts_payable").fillna(0)
        + ctx.avg4("notes_payable").fillna(0)
        + ctx.avg4("prepayments").fillna(0)
    )
    return ind.safe_div(ctx.ttm("cost"), base)


@factor("accounts_payable_turnover_days")
def accounts_payable_turnover_days(ctx: FactorContext) -> pd.DataFrame:
    return 360 / accounts_payable_turnover_rate(ctx)


@factor("OperatingCycle")
def operating_cycle(ctx: FactorContext) -> pd.DataFrame:
    return account_receivable_turnover_days(ctx) + inventory_turnover_days(ctx)


@factor("total_profit_to_cost_ratio")
def total_profit_to_cost_ratio(ctx: FactorContext) -> pd.DataFrame:
    cost = (
        ctx.ttm("cost")
        + ctx.ttm("financial_expense")
        + ctx.ttm("selling_expense")
        + ctx.ttm("admin_expense")
    )
    return ind.safe_div(ctx.ttm("total_profit"), cost)


# ---------------------------------------------------------------- 规模 / 每股


@factor("size")
def size(ctx: FactorContext) -> pd.DataFrame:
    assets = ctx.point("total_assets")
    return np.log(assets.where(assets > 0))


@factor("total_operating_revenue_per_share_ttm")
def total_operating_revenue_per_share_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("total_revenue"), ctx.shares)


@factor("operating_revenue_per_share_ttm")
def operating_revenue_per_share_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.shares)


@factor("total_operating_revenue_per_share")
def total_operating_revenue_per_share(ctx: FactorContext) -> pd.DataFrame:
    return total_operating_revenue_per_share_ttm(ctx)


@factor("operating_revenue_per_share")
def operating_revenue_per_share(ctx: FactorContext) -> pd.DataFrame:
    return operating_revenue_per_share_ttm(ctx)


@factor("operating_profit_per_share_ttm")
def operating_profit_per_share_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("operating_profit"), ctx.shares)


@factor("operating_profit_per_share")
def operating_profit_per_share(ctx: FactorContext) -> pd.DataFrame:
    return operating_profit_per_share_ttm(ctx)


@factor("eps_ttm")
def eps_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit_parent"), ctx.shares)


@factor("net_asset_per_share")
def net_asset_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("equity_parent"), ctx.shares)


@factor("cash_and_equivalents_per_share")
def cash_and_equivalents_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("cash_end"), ctx.shares)


@factor("cashflow_per_share_ttm")
def cashflow_per_share_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_cash_increase"), ctx.shares)


@factor("net_operate_cash_flow_per_share")
def net_operate_cash_flow_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.shares)


@factor("surplus_reserve_fund_per_share")
def surplus_reserve_fund_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("surplus_reserve"), ctx.shares)


@factor("retained_profit_per_share")
def retained_profit_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("retained_profit"), ctx.shares)


@factor("retained_earnings_per_share")
def retained_earnings_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(retained_earnings(ctx), ctx.shares)


@factor("capital_reserve_fund_per_share")
def capital_reserve_fund_per_share(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("capital_reserve"), ctx.shares)


@factor("retained_earnings")
def retained_earnings(ctx: FactorContext) -> pd.DataFrame:
    return ctx.point("surplus_reserve").fillna(0) + ctx.point("retained_profit").fillna(0)


# ---------------------------------------------------------------- 现金流


@factor("net_operate_cash_flow_ttm")
def net_operate_cash_flow_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("cfo")


@factor("net_invest_cash_flow_ttm")
def net_invest_cash_flow_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("cfi")


@factor("net_finance_cash_flow_ttm")
def net_finance_cash_flow_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("cff")


@factor("cfo_to_ev")
def cfo_to_ev(ctx: FactorContext) -> pd.DataFrame:
    enterprise_value = (
        ctx.market_cap + ctx.point("total_liabilities") - ctx.point("cash")
    )
    return ind.safe_div(ctx.ttm("cfo"), enterprise_value)


@factor("net_operate_cash_flow_to_operate_income")
def net_operate_cash_flow_to_operate_income(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.ttm("total_revenue") - ctx.ttm("total_cost"))


@factor("net_operating_cash_flow_coverage")
def net_operating_cash_flow_coverage(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.ttm("net_profit_parent"))


@factor("net_operate_cash_flow_to_net_debt")
def net_operate_cash_flow_to_net_debt(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), total_debt(ctx) - ctx.point("cash"))


@factor("net_operate_cash_flow_to_asset")
def net_operate_cash_flow_to_asset(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.point("total_assets"))


@factor("net_operate_cash_flow_to_total_liability")
def net_operate_cash_flow_to_total_liability(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.point("total_liabilities"))


@factor("net_operate_cash_flow_to_total_current_liability")
def net_operate_cash_flow_to_total_current_liability(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.point("current_liabilities"))


@factor("cash_rate_of_sales")
def cash_rate_of_sales(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.ttm("revenue"))


@factor("cash_to_current_liability")
def cash_to_current_liability(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("cash"), ctx.avg4("current_liabilities"))


@factor("ACCA")
def acca(ctx: FactorContext) -> pd.DataFrame:
    assets = ctx.point("total_assets")
    return ind.safe_div(ctx.ttm("cfo"), assets) - ind.safe_div(ctx.ttm("net_profit"), assets)


@factor("goods_service_cash_to_operating_revenue_ttm")
def goods_service_cash_to_operating_revenue_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cash_from_sales"), ctx.ttm("revenue"))


@factor("goods_sale_and_service_render_cash_ttm")
def goods_sale_and_service_render_cash_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("cash_from_sales")


# ---------------------------------------------------------------- 偿债 / 资本结构


@factor("net_working_capital")
def net_working_capital(ctx: FactorContext) -> pd.DataFrame:
    return ctx.point("current_assets") - ctx.point("current_liabilities")


@factor("quick_ratio")
def quick_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.point("current_assets") - ctx.point("inventory"), ctx.point("current_liabilities")
    )


@factor("current_ratio")
def current_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("current_assets"), ctx.point("current_liabilities"))


@factor("super_quick_ratio")
def super_quick_ratio(ctx: FactorContext) -> pd.DataFrame:
    liquid = (
        ctx.point("cash").fillna(0)
        + ctx.point("financial_assets_trading").fillna(0)
        + ctx.point("notes_receivable").fillna(0)
        + ctx.point("accounts_receivable").fillna(0)
        + ctx.point("other_receivables").fillna(0)
    )
    return ind.safe_div(liquid, ctx.point("current_liabilities"))


@factor("debt_to_asset_ratio")
def debt_to_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    return debt_to_asset(ctx)


@factor("debt_to_assets")
def debt_to_assets(ctx: FactorContext) -> pd.DataFrame:
    return debt_to_asset(ctx)


@factor("debt_to_equity_ratio")
def debt_to_equity_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("total_liabilities"), ctx.point("equity_parent"))


@factor("equity_to_asset_ratio")
def equity_to_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("total_equity"), ctx.point("total_assets"))


@factor("equity_to_fixed_asset_ratio")
def equity_to_fixed_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.point("fixed_assets").fillna(0)
        + ctx.point("construction_in_progress").fillna(0)
        + ctx.point("construction_materials").fillna(0)
    )
    return ind.safe_div(ctx.point("total_equity"), base)


@factor("debt_to_tangible_equity_ratio")
def debt_to_tangible_equity_ratio(ctx: FactorContext) -> pd.DataFrame:
    tangible = (
        ctx.point("total_equity")
        - ctx.point("intangible_assets").fillna(0)
        - ctx.point("goodwill").fillna(0)
    )
    return ind.safe_div(ctx.point("total_liabilities"), tangible)


@factor("long_debt_to_working_capital_ratio")
def long_debt_to_working_capital_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.point("non_current_liabilities"),
        ctx.point("current_assets") - ctx.point("current_liabilities"),
    )


@factor("long_debt_to_asset_ratio")
def long_debt_to_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("long_term_borrowings"), ctx.point("total_assets"))


@factor("long_term_debt_to_asset_ratio")
def long_term_debt_to_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("non_current_liabilities"), ctx.point("total_assets"))


@factor("MLEV")
def mlev(ctx: FactorContext) -> pd.DataFrame:
    return market_leverage(ctx)


@factor("market_leverage")
def market_leverage_factor(ctx: FactorContext) -> pd.DataFrame:
    return market_leverage(ctx)


@factor("book_leverage")
def book_leverage_factor(ctx: FactorContext) -> pd.DataFrame:
    return book_leverage(ctx)


@factor("leverage")
def leverage(ctx: FactorContext) -> pd.DataFrame:
    return 0.38 * market_leverage(ctx) + 0.35 * debt_to_asset(ctx) + 0.27 * book_leverage(ctx)


@factor("financial_leverage")
def financial_leverage(ctx: FactorContext) -> pd.DataFrame:
    return 0.40 * debt_to_asset(ctx) + 0.30 * book_leverage(ctx) + 0.30 * market_leverage(ctx)


@factor("net_debt")
def net_debt(ctx: FactorContext) -> pd.DataFrame:
    return total_debt(ctx) - ctx.point("cash")


@factor("interest_carry_current_liability")
def interest_carry_current_liability(ctx: FactorContext) -> pd.DataFrame:
    return ctx.point("current_liabilities") - interest_free_current_liability(ctx)


@factor("interest_free_current_liability")
def interest_free_current_liability_factor(ctx: FactorContext) -> pd.DataFrame:
    return interest_free_current_liability(ctx)


@factor("financial_assets")
def financial_assets_factor(ctx: FactorContext) -> pd.DataFrame:
    return financial_assets(ctx)


@factor("financial_liability")
def financial_liability_factor(ctx: FactorContext) -> pd.DataFrame:
    return financial_liability(ctx)


@factor("operating_assets")
def operating_assets(ctx: FactorContext) -> pd.DataFrame:
    return ctx.point("total_assets") - financial_assets(ctx)


@factor("operating_liability")
def operating_liability(ctx: FactorContext) -> pd.DataFrame:
    return ctx.point("total_liabilities") - financial_liability(ctx)


# ---------------------------------------------------------------- 利润表科目


@factor("total_operating_revenue_ttm")
def total_operating_revenue_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("total_revenue")


@factor("operating_revenue_ttm")
def operating_revenue_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("revenue")


@factor("operating_profit_ttm")
def operating_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("operating_profit")


@factor("total_profit_ttm")
def total_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("total_profit")


@factor("net_profit_ttm")
def net_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("net_profit")


@factor("np_parent_company_owners_ttm")
def np_parent_company_owners_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("net_profit_parent")


@factor("operating_cost_ttm")
def operating_cost_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("cost")


@factor("total_operating_cost_ttm")
def total_operating_cost_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("total_cost")


@factor("sale_expense_ttm")
def sale_expense_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("selling_expense")


@factor("administration_expense_ttm")
def administration_expense_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("admin_expense")


@factor("financial_expense_ttm")
def financial_expense_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("financial_expense")


@factor("asset_impairment_loss_ttm")
def asset_impairment_loss_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("asset_impairment")


@factor("value_change_profit_ttm")
def value_change_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("fair_value_change")


@factor("non_operating_net_profit_ttm")
def non_operating_net_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("non_operating_income") - ctx.ttm("non_operating_expense")


@factor("gross_profit_ttm")
def gross_profit_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("revenue") - ctx.ttm("cost")


@factor("EBIT")
def ebit(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("net_profit") + ctx.ttm("income_tax") + ctx.ttm("financial_expense")


@factor("EBITDA")
def ebitda(ctx: FactorContext) -> pd.DataFrame:
    return ctx.ttm("revenue") - ctx.ttm("cost") - ctx.ttm("tax_surcharge")


@factor("OperateNetIncome")
def operate_net_income(ctx: FactorContext) -> pd.DataFrame:
    """经营活动净收益 = 营业利润 − 投资收益 − 公允价值变动收益。"""
    return (
        ctx.ttm("operating_profit")
        - ctx.ttm("investment_income").fillna(0)
        - ctx.ttm("fair_value_change").fillna(0)
    )


# ---------------------------------------------------------------- 结构与效率比率


@factor("sale_expense_to_operating_revenue")
def sale_expense_to_operating_revenue(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("selling_expense"), ctx.ttm("total_revenue"))


@factor("admin_expense_rate")
def admin_expense_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("admin_expense"), ctx.ttm("total_revenue"))


@factor("financial_expense_rate")
def financial_expense_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("financial_expense"), ctx.ttm("total_revenue"))


@factor("operating_tax_to_operating_revenue_ratio_ttm")
def operating_tax_to_operating_revenue_ratio_ttm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("tax_surcharge"), ctx.ttm("revenue"))


@factor("net_non_operating_income_to_total_profit")
def net_non_operating_income_to_total_profit(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.ttm("non_operating_income") - ctx.ttm("non_operating_expense"),
        ctx.ttm("total_profit"),
    )


@factor("operating_profit_to_total_profit")
def operating_profit_to_total_profit(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("operating_profit"), ctx.ttm("total_profit"))


@factor("invest_income_associates_to_total_profit")
def invest_income_associates_to_total_profit(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("associates_income"), ctx.ttm("total_profit"))


@factor("fixed_asset_ratio")
def fixed_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.point("fixed_assets").fillna(0)
        + ctx.point("construction_materials").fillna(0)
        + ctx.point("construction_in_progress").fillna(0)
    )
    return ind.safe_div(base, ctx.point("total_assets"))


@factor("intangible_asset_ratio")
def intangible_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    base = (
        ctx.point("intangible_assets").fillna(0)
        + ctx.point("development_expense").fillna(0)
        + ctx.point("goodwill").fillna(0)
    )
    return ind.safe_div(base, ctx.point("total_assets"))


@factor("non_current_asset_ratio")
def non_current_asset_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("non_current_assets"), ctx.point("total_assets"))


# ---------------------------------------------------------------- 估值


@factor("book_to_price_ratio")
def book_to_price_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("equity_parent"), ctx.market_cap)


@factor("btop")
def btop(ctx: FactorContext) -> pd.DataFrame:
    return book_to_price_ratio(ctx)


@factor("earnings_to_price_ratio")
def earnings_to_price_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("net_profit"), ctx.market_cap)


@factor("cash_earnings_to_price_ratio")
def cash_earnings_to_price_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.market_cap)


@factor("cash_flow_to_price_ratio")
def cash_flow_to_price_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("cfo"), ctx.market_cap)


@factor("sales_to_price_ratio")
def sales_to_price_ratio(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.ttm("revenue"), ctx.market_cap)


@factor("PEG")
def peg(ctx: FactorContext) -> pd.DataFrame:
    pe = ind.safe_div(ctx.market_cap, ctx.ttm("net_profit_parent"))
    growth = ctx.growth("net_profit_parent") * 100
    return ind.safe_div(pe, growth)


# ---------------------------------------------------------------- 增长


@factor("operating_revenue_growth_rate")
def operating_revenue_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("revenue")


@factor("net_profit_growth_rate")
def net_profit_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("net_profit")


@factor("np_parent_company_owners_growth_rate")
def np_parent_company_owners_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("net_profit_parent")


@factor("operating_profit_growth_rate")
def operating_profit_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("operating_profit")


@factor("total_profit_growth_rate")
def total_profit_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("total_profit")


@factor("net_operate_cashflow_growth_rate")
def net_operate_cashflow_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("cfo")


@factor("financing_cash_growth_rate")
def financing_cash_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ctx.growth("cff")


@factor("total_asset_growth_rate")
def total_asset_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("total_assets"), ctx.point("total_assets", lag_q=4)) - 1


@factor("net_asset_growth_rate")
def net_asset_growth_rate(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.point("total_equity"), ctx.point("total_equity", lag_q=4)) - 1


@factor("DEGM")
def degm(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(gross_margin_ttm(ctx), gross_margin_ttm(ctx, lag_q=4)) - 1


# ---------------------------------------------------------------- 长期指标（8 年）


def _annual_values(ctx: FactorContext, field: str) -> pd.DataFrame:
    return ctx.financial.annual_frame(field)


def _geometric_mean(frame: pd.DataFrame, years: int) -> pd.DataFrame:
    return np.exp(np.log1p(frame).rolling(years, min_periods=years).mean()) - 1


@factor("roe_ttm_8y")
def roe_ttm_8y(ctx: FactorContext) -> pd.DataFrame:
    net_profit = _annual_values(ctx, "net_profit")
    equity = _annual_values(ctx, "total_equity")
    annual_roe = ind.safe_div(net_profit, equity)
    result = _geometric_mean(annual_roe, 8)
    return ctx.financial.align_annual(result)


@factor("roa_ttm_8y")
def roa_ttm_8y(ctx: FactorContext) -> pd.DataFrame:
    net_profit = _annual_values(ctx, "net_profit")
    assets = _annual_values(ctx, "total_assets")
    annual_roa = ind.safe_div(net_profit, assets)
    result = _geometric_mean(annual_roa, 8)
    return ctx.financial.align_annual(result)


@factor("DEGM_8y")
def degm_8y(ctx: FactorContext) -> pd.DataFrame:
    revenue = _annual_values(ctx, "revenue")
    cost = _annual_values(ctx, "cost")
    margin = ind.safe_div(revenue - cost, revenue)
    growth = ind.safe_div(margin, margin.shift(1)) - 1
    result = _geometric_mean(growth, 8)
    return ctx.financial.align_annual(result)


@factor("margin_stability")
def margin_stability(ctx: FactorContext) -> pd.DataFrame:
    revenue = _annual_values(ctx, "revenue")
    cost = _annual_values(ctx, "cost")
    margin = ind.safe_div(revenue - cost, revenue)
    result = ind.safe_div(
        margin.rolling(8, min_periods=4).mean(), margin.rolling(8, min_periods=4).std(ddof=0)
    )
    return ctx.financial.align_annual(result)


@factor("maximum_margin")
def maximum_margin(ctx: FactorContext) -> pd.DataFrame:
    return np.maximum(margin_stability(ctx), degm_8y(ctx))


@factor("earnings_growth")
def earnings_growth(ctx: FactorContext) -> pd.DataFrame:
    """过去 5 个财年 EPS 平均增速 ÷ 年均 EPS。"""
    eps = _annual_values(ctx, "eps")
    eps = eps.where(eps.abs() > 1e-6)
    growth = ind.safe_div(eps, eps.shift(1)) - 1
    average_growth = growth.rolling(5, min_periods=5).mean()
    average_eps = eps.rolling(5, min_periods=5).mean().abs()
    result = ind.safe_div(average_growth, average_eps)
    return ctx.financial.align_annual(result)


@factor("sales_growth")
def sales_growth(ctx: FactorContext) -> pd.DataFrame:
    revenue = _annual_values(ctx, "revenue")
    eps = _annual_values(ctx, "eps")
    net_profit = _annual_values(ctx, "net_profit_parent")
    shares = ind.safe_div(net_profit, eps.where(eps.abs() > 1e-6))
    revenue_per_share = ind.safe_div(revenue, shares)
    growth = ind.safe_div(revenue_per_share, revenue_per_share.shift(1)) - 1
    result = ind.safe_div(
        growth.rolling(5, min_periods=5).mean(),
        revenue_per_share.rolling(5, min_periods=5).mean().abs(),
    )
    return ctx.financial.align_annual(result)


# ---------------------------------------------------------------- 财报质量（Beneish 类）


@factor("LVGI")
def lvgi(ctx: FactorContext) -> pd.DataFrame:
    current = _annual_values(ctx, "total_liabilities") / _annual_values(ctx, "total_assets")
    previous = current.shift(1)
    return ctx.financial.align_annual(ind.safe_div(current, previous))


@factor("SGI")
def sgi(ctx: FactorContext) -> pd.DataFrame:
    revenue = _annual_values(ctx, "revenue")
    return ctx.financial.align_annual(ind.safe_div(revenue, revenue.shift(1)))


@factor("GMI")
def gmi(ctx: FactorContext) -> pd.DataFrame:
    revenue = _annual_values(ctx, "revenue")
    cost = _annual_values(ctx, "cost")
    margin = ind.safe_div(revenue - cost, revenue)
    return ctx.financial.align_annual(ind.safe_div(margin.shift(1), margin))


@factor("DSRI")
def dsri(ctx: FactorContext) -> pd.DataFrame:
    receivable = _annual_values(ctx, "accounts_receivable")
    revenue = _annual_values(ctx, "revenue")
    ratio = ind.safe_div(receivable, revenue)
    return ctx.financial.align_annual(ind.safe_div(ratio, ratio.shift(1)))


@factor("SGAI")
def sgai(ctx: FactorContext) -> pd.DataFrame:
    selling = _annual_values(ctx, "selling_expense")
    admin = _annual_values(ctx, "admin_expense")
    revenue = _annual_values(ctx, "revenue")
    ratio = ind.safe_div(selling.fillna(0) + admin.fillna(0), revenue)
    return ctx.financial.align_annual(ind.safe_div(ratio, ratio.shift(1)))

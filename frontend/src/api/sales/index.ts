import { del, get, patch, post, put } from '@/utils/request'
import type { PageData } from '@/types/api'
import type {
  Customer,
  Forecast,
  ForecastSummary,
  Order,
  Product,
  ProductPrice,
  ProductPriceHistory,
  SalesReturn,
  SalesStats,
  Shipment,
} from '@/types/erp'

/** sales 模块接口（销售管理），统一前缀 /api/v1/sales */

export function getSalesStats(): Promise<SalesStats> {
  return get<SalesStats>('/sales/stats')
}

// ---------------- 客户 ----------------

export function listCustomers(params: Record<string, unknown> = {}): Promise<PageData<Customer>> {
  return get<PageData<Customer>>('/sales/customers', params)
}

export function createCustomer(payload: Record<string, unknown>): Promise<Customer> {
  return post<Customer>('/sales/customers', payload)
}

export function updateCustomer(id: number, payload: Record<string, unknown>): Promise<Customer> {
  return put<Customer>(`/sales/customers/${id}`, payload)
}

export function setCustomerStatus(id: number, status: string, operatorId?: number): Promise<Customer> {
  return patch<Customer>(`/sales/customers/${id}/status`, { status, operator_id: operatorId })
}

export function deleteCustomer(id: number, operatorId?: number): Promise<void> {
  return del<void>(`/sales/customers/${id}`, { params: { operator_id: operatorId } })
}

// ---------------- 销售产品 ----------------

export function listProducts(params: Record<string, unknown> = {}): Promise<Product[]> {
  return get<Product[]>('/sales/products', params)
}

// ---------------- 产品价格 ----------------

export function listProductPrices(
  params: Record<string, unknown> = {},
): Promise<PageData<ProductPrice>> {
  return get<PageData<ProductPrice>>('/sales/product-prices', params)
}

/** 查询单个物料的当前价格（销售订单选择物料时带出单价） */
export function getProductPrice(materialId: number): Promise<ProductPrice> {
  return get<ProductPrice>(`/sales/product-prices/${materialId}`)
}

export function updateProductPrice(
  materialId: number,
  payload: Record<string, unknown>,
): Promise<ProductPrice> {
  return put<ProductPrice>(`/sales/product-prices/${materialId}`, payload)
}

export function listProductPriceHistory(materialId: number): Promise<ProductPriceHistory[]> {
  return get<ProductPriceHistory[]>(`/sales/product-prices/${materialId}/history`)
}

export function deleteProductPrice(materialId: number, operatorId?: number): Promise<null> {
  return del<null>(`/sales/product-prices/${materialId}`, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 销售预测 ----------------

export function listForecasts(params: Record<string, unknown> = {}): Promise<PageData<Forecast>> {
  return get<PageData<Forecast>>('/sales/forecasts', params)
}

/** 销售预测按销售类别（整机 / 可售备件 / 内部件）汇总 */
export function getForecastSummary(
  params: Record<string, unknown> = {},
): Promise<ForecastSummary[]> {
  return get<ForecastSummary[]>('/sales/forecasts/summary', params)
}

export function createForecast(payload: Record<string, unknown>): Promise<Forecast> {
  return post<Forecast>('/sales/forecasts', payload)
}

export function updateForecast(id: number, payload: Record<string, unknown>): Promise<Forecast> {
  return put<Forecast>(`/sales/forecasts/${id}`, payload)
}

export function setForecastStatus(id: number, status: string, operatorId?: number): Promise<Forecast> {
  return patch<Forecast>(`/sales/forecasts/${id}/status`, { status, operator_id: operatorId })
}

export function deleteForecast(id: number): Promise<null> {
  return del<null>(`/sales/forecasts/${id}`)
}

// ---------------- 销售订单 ----------------

export function listOrders(params: Record<string, unknown> = {}): Promise<PageData<Order>> {
  return get<PageData<Order>>('/sales/orders', params)
}

export function getOrder(id: number): Promise<Order> {
  return get<Order>(`/sales/orders/${id}`)
}

export function createOrder(payload: Record<string, unknown>): Promise<Order> {
  return post<Order>('/sales/orders', payload)
}

export function updateOrder(id: number, payload: Record<string, unknown>): Promise<Order> {
  return put<Order>(`/sales/orders/${id}`, payload)
}

export function deleteOrder(id: number): Promise<null> {
  return del<null>(`/sales/orders/${id}`)
}

export function setOrderStatus(id: number, status: string, operatorId?: number): Promise<Order> {
  return patch<Order>(`/sales/orders/${id}/status`, { status, operator_id: operatorId })
}

// ---------------- 销售发货 ----------------

export function listShipments(params: Record<string, unknown> = {}): Promise<PageData<Shipment>> {
  return get<PageData<Shipment>>('/sales/shipments', params)
}

export function getShipment(id: number): Promise<Shipment> {
  return get<Shipment>(`/sales/shipments/${id}`)
}

export function createShipment(payload: Record<string, unknown>): Promise<Shipment> {
  return post<Shipment>('/sales/shipments', payload)
}

export function confirmShipment(id: number, operatorId?: number): Promise<Shipment> {
  return post<Shipment>(`/sales/shipments/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelShipment(id: number, operatorId?: number): Promise<Shipment> {
  return post<Shipment>(`/sales/shipments/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 销售退货 ----------------

export function listReturns(params: Record<string, unknown> = {}): Promise<PageData<SalesReturn>> {
  return get<PageData<SalesReturn>>('/sales/returns', params)
}

export function getReturn(id: number): Promise<SalesReturn> {
  return get<SalesReturn>(`/sales/returns/${id}`)
}

export function createReturn(payload: Record<string, unknown>): Promise<SalesReturn> {
  return post<SalesReturn>('/sales/returns', payload)
}

export function confirmReturn(id: number, operatorId?: number): Promise<SalesReturn> {
  return post<SalesReturn>(`/sales/returns/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelReturn(id: number, operatorId?: number): Promise<SalesReturn> {
  return post<SalesReturn>(`/sales/returns/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}
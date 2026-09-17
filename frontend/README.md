# BH-ERP 前端（Vue 3 + Vite + TypeScript）

基础工程框架，**不含任何 ERP 业务实现**，五个模块均为占位页面。

## 技术栈

Vue 3 · Vite 6 · TypeScript · Pinia · Vue Router 4 · Axios · Element Plus

## 目录结构

```
frontend/
├── src/
│   ├── api/                    # 接口层，按模块划分
│   │   ├── system/ sales/ planning/ procurement/ inventory/
│   ├── views/                  # 页面，按模块划分
│   │   ├── dashboard/          # 工作台
│   │   ├── login/              # 登录前页面（占位）
│   │   ├── error/              # 404
│   │   └── system/ sales/ planning/ procurement/ inventory/
│   ├── components/common/      # 跨模块公共组件（如 ModulePlaceholder）
│   ├── layouts/                # BasicLayout + AppHeader + AppSidebar + menu.ts
│   ├── router/                 # index.ts（路由实例）、routes.ts（路由表）
│   ├── stores/                 # Pinia：index.ts、modules/app.ts
│   ├── types/                  # api.ts（统一响应/分页）、router.d.ts
│   ├── utils/                  # request.ts（axios 实例）
│   ├── styles/index.css
│   ├── App.vue
│   └── main.ts
├── index.html
├── package.json
├── vite.config.ts
└── .env.example
```

## 启动

```bash
cd frontend
npm install
copy .env.example .env      # Windows（macOS/Linux 用 cp）
npm run dev                 # http://127.0.0.1:5173
```

开发服务器已把 `/api` 代理到 `http://127.0.0.1:8000`，直接启动后端即可联调。

其他命令：

```bash
npm run type-check   # 仅类型检查
npm run build        # 类型检查 + 生产构建
npm run preview      # 预览构建产物
```

## 路由约定

| 路径 | 归属模块 |
| --- | --- |
| `/login` | 登录前页面（占位） |
| `/dashboard` | 工作台 |
| `/system` | system |
| `/sales` | sales |
| `/planning` | planning |
| `/procurement` | procurement |
| `/inventory` | inventory |

新增页面请在自己模块的路由节点下加**子路由**，例如销售订单：

```ts
// router/routes.ts 中的 sales 节点
{
  path: 'sales',
  name: 'Sales',
  component: () => import('@/views/sales/index.vue'),
  children: [
    { path: 'orders', name: 'SalesOrder', component: () => import('@/views/sales/order/index.vue') },
  ],
}
```

## 接口调用约定

1. 所有请求走 `@/utils/request.ts` 中的 axios 实例，它会自动拆包统一响应 `{ code, message, data }`，
   业务代码直接拿到 `data`；`code !== 0` 会 reject 一个 `Error`。
2. 接口函数写在 `@/api/<module>/` 下，一个业务实体一个文件。
3. 后端接口前缀统一 `/api/v1`，`baseURL` 由 `VITE_API_BASE_URL` 控制。

```ts
// src/api/sales/order.ts
import type { PageData } from '@/types/api'
import { get } from '@/utils/request'

export function listSalesOrders(params: { page: number; page_size: number }) {
  return get<PageData<{ id: number }>>('/sales/orders', params)
}
```

## 不要改的文件

以下文件被五个模块共用，修改前请先在群里沟通：

`src/utils/`、`src/types/`、`src/components/common/`、`src/stores/index.ts`、
`src/layouts/`、`src/router/`、`vite.config.ts`、`tsconfig*.json`、`package.json`

侧边栏菜单如需新增条目，改 `src/layouts/menu.ts`，但**只在自己模块的条目内部扩展**。

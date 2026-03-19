# PDFtoDeck — MVP 需求文档

版本：v0.1
日期：2026-03-19
状态：Draft

## 1. 产品概述

### 1.1 产品定位

PDFtoDeck 是一个在线 PDF → PPT 转换工具，核心差异化在于：不仅提取文字和图片，还能将 PDF 中的小尺寸矢量图形（icon）还原为 PPT 中可编辑的 Freeform Shape，用户可直接修改颜色和形状。

### 1.2 目标用户

海外用户，主要场景：
- 设计师/市场人员：收到 PDF 版的演示文稿，需要二次编辑
- 学生/教师：将 PDF 课件转为可编辑的 PPT
- 商务人士：修改客户发来的 PDF 提案

### 1.3 商业模式

免费增值（Freemium）：
- 免费版：每日 3 次转换，单文件 ≤ 10 页，≤ 20MB
- 付费版：无限次转换，无页数/大小限制，优先队列，批量转换

## 2. MVP 功能范围

### 2.1 核心功能（Must Have）

**F1 - PDF 文件上传**
- 支持拖拽上传和点击选择
- 支持格式：.pdf
- 文件大小限制：免费用户 ≤ 20MB
- 页数限制：免费用户 ≤ 10 页
- 上传后显示文件名、大小、页数预览

**F2 - PDF 解析与元素提取**
- 文字提取：保留字体大小、粗细、颜色、位置信息
- 图片提取：提取嵌入的位图（JPEG/PNG），保留原始分辨率和位置
- 矢量路径提取：识别 PDF 中的 Path 对象，区分 icon 和大图

**F3 - Icon 智能识别与还原**
- 面积阈值过滤：占页面面积 ≤ 阈值（默认 5%）的矢量路径视为 icon
- 方案 A（默认）：路径节点数 ≤ 50，转为 PPT Freeform Shape（可编辑颜色/形状）
- 方案 B（降级）：路径节点数 > 50，转为 SVG 图片嵌入 PPT
- 超过面积阈值的矢量图形作为普通图片处理

**F4 - PPT 生成**
- 输出格式：.pptx（Office Open XML）
- 页面尺寸：与原 PDF 页面比例一致（默认 16:9 或 4:3）
- 元素布局：尽可能还原 PDF 中各元素的相对位置
- 文字框：保留字体大小、颜色，可编辑
- 图片：保留原始分辨率，可替换
- Icon Shape：可编辑填充颜色、描边颜色、形状

**F5 - 文件下载**
- 转换完成后提供 .pptx 下载链接
- 下载链接有效期：1 小时
- 文件自动清理：服务端 1 小时后删除

### 2.2 用户可调参数

**P1 - Icon 面积阈值**
- 类型：滑块（Slider）
- 范围：1% - 20%
- 默认值：5%
- 说明文字："Elements smaller than this percentage of the page will be converted to editable shapes"

### 2.3 非功能需求

**性能**
- 单次转换（20 页 PDF）：≤ 10 秒
- 并发支持：≥ 3 个同时转换任务
- 文件上传速度：受用户网络限制，前端显示进度条

**安全**
- 上传文件 1 小时后自动删除
- 不存储用户个人信息（免费版无需注册）
- HTTPS 全站加密
- 文件传输使用临时签名 URL

**SEO**
- 首页 SSR/SSG 渲染，确保搜索引擎可索引
- 核心关键词：pdf to ppt, pdf to powerpoint, convert pdf to editable ppt
- 页面加载时间 ≤ 2 秒（Lighthouse Performance ≥ 90）

## 3. 技术架构

### 3.1 系统架构

```
用户浏览器
  → Cloudflare Pages（Next.js 前端）
    → Cloudflare Workers（API 网关 / 鉴权 / 限流）
      → VPS 2核4G（Python FastAPI 转换服务）
        → Cloudflare R2（文件存储）
```

### 3.2 前端技术栈

- 框架：Next.js (App Router)
- 样式：Tailwind CSS
- 部署：Cloudflare Pages
- 关键组件：文件拖拽上传、参数滑块、转换进度条、下载按钮

### 3.3 后端技术栈

- 框架：Python FastAPI
- PDF 解析：pymupdf (fitz)
- PPT 生成：python-pptx
- 任务队列：asyncio Queue（MVP 阶段，后续可升级 Celery）
- 部署：VPS (Docker)

### 3.4 API 网关

- Cloudflare Workers
- 职责：请求鉴权、频率限制（免费用户 3次/天）、请求转发

### 3.5 文件存储

- Cloudflare R2
- 上传的 PDF 和生成的 PPTX 临时存储
- TTL：1 小时自动清理

## 4. 页面设计

### 4.1 首页 (/)

- Hero 区域：标题 "Convert PDF to Editable PowerPoint" + 副标题
- 上传区域：大面积拖拽区，支持点击选择
- 功能亮点：3 个卡片（Editable Shapes / Preserved Layout / Free & Fast）
- Footer：隐私政策、联系方式

### 4.2 转换页 (/convert)

- 文件信息：文件名、大小、页数
- 参数设置：Icon 面积阈值滑块
- 转换按钮 + 进度条
- 转换完成：下载按钮 + 预览缩略图（可选）

## 5. API 设计

### 5.1 上传 PDF

```
POST /api/upload
Content-Type: multipart/form-data
Body: file (PDF)
Response: { "task_id": "xxx", "pages": 10, "size_mb": 2.5 }
```

### 5.2 开始转换

```
POST /api/convert
Body: { "task_id": "xxx", "icon_threshold": 0.05 }
Response: { "status": "processing" }
```

### 5.3 查询进度

```
GET /api/status/{task_id}
Response: { "status": "processing", "progress": 60, "current_page": 6, "total_pages": 10 }
```

### 5.4 下载结果

```
GET /api/download/{task_id}
Response: 302 → R2 签名 URL
```

## 6. 免费增值限制

| 功能 | 免费版 | 付费版 |
| --- | --- | --- |
| 每日转换次数 | 3 次 | 无限 |
| 单文件页数 | ≤ 10 页 | 无限 |
| 单文件大小 | ≤ 20MB | ≤ 200MB |
| Icon 可编辑还原 | ✓ | ✓ |
| 批量转换 | ✗ | ✓ |
| 优先队列 | ✗ | ✓ |
| 无水印 | ✓ | ✓ |

## 7. MVP 里程碑

- M1（第 1-2 周）：后端 PDF 解析 + PPT 生成核心模块，本地可运行
- M2（第 3 周）：前端页面 + API 网关，端到端流程跑通
- M3（第 4 周）：部署上线 + 免费增值限制 + 基础 SEO
- M4（第 5-6 周）：Phase 2 矢量 icon 还原功能

## 8. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 复杂 PDF 解析失败 | 转换结果不可用 | 增加错误处理，返回"部分转换"结果 |
| 矢量路径还原变形 | Icon 不可用 | 自动降级为方案 B（SVG 图片） |
| VPS 并发不足 | 用户等待过长 | 任务队列 + 排队提示 + 付费优先 |
| 大文件内存溢出 | 服务崩溃 | 限制文件大小 + 分页处理 + OOM 保护 |

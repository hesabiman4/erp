from django.urls import path,re_path
from erp.access_control import AccessControlAPI
from erp.tax_api import TaxSchedulesAPI
from erp.credit_management import CreditAPI
from erp.document_register import DocumentRegisterAPI
from erp.stock_register import StockRegisterAPI
from erp.correction_guidance import CorrectionGuidanceAPI
from erp.party_api import PartyToolsAPI
from erp.order_readiness import OrderReadinessAPI
from erp.factory_review import FactoryReviewAPI
from erp.purchase_review import PurchaseReviewAPI,BillableReceiptAPI
from erp.print_settings import PrintSettingsAPI,DocumentPrintHistoryAPI
from erp.money_api import MoneyInstrumentsAPI
from erp.backup_settings import BackupSettingsAPI
from erp.lan_settings import LANSettingsAPI
from erp.daily_v6_api import AttentionAPI,TimelineAPI,TrendsAPI,BulkCatalogAPI,DraftFieldsAPI
from erp.cashier_api import CashierAPI
from erp.statement_api import StatementAPI
from erp.sourcing_api import SourcingAPI
from erp.runtime_management import RuntimeManagementAPI
from erp.calendar_periods import BusinessPeriodsAPI
from erp.advanced_planning import PlanningAPI
from erp.procurement_api import ProcurementAPI
from erp.excellence_api import ExcellenceAPI,PortalRequestsAPI
from erp.portal import PortalAPI,PortalPrintAPI,PortalAccessAPI
from erp.manual_api import AccountingGuideAPI
from erp.factory import FactoryAPI
from erp.jobs_api import JobsAPI
from erp.commissions import CommissionAPI
from erp.late_cost import LateCostAPI
from erp.foreign_extensions import ForeignExtensionAPI
from erp.crm_api import CRMAPI
from erp.counter_api import CounterSalesAPI
from erp.workspace_api import WorkspaceAPI,GuidanceAPI
from erp.capture_api import CaptureAPI
from erp.production_process import ProductionProcessAPI
from erp.dispatch_api import DispatchAPI
from django.contrib import admin
from erp import api
from erp.growth_api import GrowthAPI,CutPreviewAPI,ScanAPI
from erp.localization import CalendarAPI,PreferenceAPI
from .frontend import shell

urlpatterns=[
    path('api/tax-schedules/',TaxSchedulesAPI.as_view()),
    path('api/tax-schedules/<int:pk>/',TaxSchedulesAPI.as_view()),
    path('api/document-register/',DocumentRegisterAPI.as_view()),
    path('api/stock-register/',StockRegisterAPI.as_view()),
    path('api/factory-review/',FactoryReviewAPI.as_view()),
    path('api/purchase-review/',PurchaseReviewAPI.as_view()),
    path('api/receipts/<int:pk>/billable/',BillableReceiptAPI.as_view()),
    path('api/orders/<int:pk>/readiness/',OrderReadinessAPI.as_view()),
    path('api/party-tools/<str:section>/',PartyToolsAPI.as_view()),
    path('api/documents/<int:pk>/correction/',CorrectionGuidanceAPI.as_view()),
    path('api/credit/',CreditAPI.as_view()),
    path('api/print-settings/',PrintSettingsAPI.as_view()),
    path('api/documents/<int:pk>/print-history/',DocumentPrintHistoryAPI.as_view()),
    path('api/access-control/',AccessControlAPI.as_view()),
    path('api/money-instruments/',MoneyInstrumentsAPI.as_view()),
    path('api/backup-settings/',BackupSettingsAPI.as_view()),
    path('api/lan-settings/',LANSettingsAPI.as_view()),
    path('api/attention/',AttentionAPI.as_view()),
    path('api/trends/',TrendsAPI.as_view()),
    path('api/documents/<int:pk>/timeline/',TimelineAPI.as_view()),
    path('api/catalog-bulk/',BulkCatalogAPI.as_view()),
    path('api/documents/<int:pk>/fields/',DraftFieldsAPI.as_view()),
    path('api/production-process/',ProductionProcessAPI.as_view()),
    path('api/workspace/',WorkspaceAPI.as_view()),
    path('api/guidance/',GuidanceAPI.as_view()),
    path('api/crm/',CRMAPI.as_view()),
    path('api/captures/<str:section>/',CaptureAPI.as_view()),
    path('api/counter/<str:section>/',CounterSalesAPI.as_view()),
    path('api/cashier/',CashierAPI.as_view()),
    path('api/statements/<str:section>/',StatementAPI.as_view()),
    path('api/sourcing/<str:section>/',SourcingAPI.as_view()),
    path('api/runtime-management/',RuntimeManagementAPI.as_view()),
    path('api/business-periods/',BusinessPeriodsAPI.as_view()),
    path('api/planning/<str:section>/',PlanningAPI.as_view()),
    path('api/procurement/<str:section>/',ProcurementAPI.as_view()),
    path('api/excellence/<str:section>/',ExcellenceAPI.as_view()),
    path('api/portal-requests/',PortalRequestsAPI.as_view()),
    path('api/late-costs/',LateCostAPI.as_view()),
    path('api/jobs/<str:section>/',JobsAPI.as_view()),
    path('api/commissions/',CommissionAPI.as_view()),
    path('api/foreign/extensions/',ForeignExtensionAPI.as_view()),
    path('api/dispatch/<str:section>/',DispatchAPI.as_view()),
    path('api/factory/',FactoryAPI.as_view()),
    path('api/accounting-guide/',AccountingGuideAPI.as_view()),
    path('api/portal/',PortalAPI.as_view()),
    path('api/portal/<int:pk>/',PortalAPI.as_view()),
    path('api/portal/<int:pk>/print/',PortalPrintAPI.as_view()),
    path('api/portal-access/',PortalAccessAPI.as_view()),
    path('api/calendar/',CalendarAPI.as_view()),
    path('api/preferences/',PreferenceAPI.as_view()),
    path('api/growth/<str:section>/',GrowthAPI.as_view()),
    path('api/cut-preview/',CutPreviewAPI.as_view()),
    path('api/scan/',ScanAPI.as_view()),
    path('admin/',admin.site.urls),
    path('api/session/',api.SessionAPI.as_view()),
    path('api/logout/',api.LogoutAPI.as_view()),
    path('api/context/',api.ContextAPI.as_view()),
    path('api/catalog/',api.CatalogAPI.as_view()),
    path('api/catalog/<str:resource>/',api.CatalogAPI.as_view()),
    path('api/catalog/<str:resource>/<int:pk>/',api.CatalogAPI.as_view()),
    path('api/business/',api.BusinessSettingsAPI.as_view()),
    path('api/businesses/',api.BusinessesAPI.as_view()),
    path('api/setup/',api.SetupAPI.as_view()),
    path('api/documents/',api.DocumentsAPI.as_view()),
    path('api/documents/<int:pk>/',api.DocumentsAPI.as_view()),
    path('api/documents/<int:pk>/print/',api.PrintAPI.as_view()),
    path('api/documents/<int:pk>/post/',api.DraftPostAPI.as_view()),
    path('api/operations/<str:action>/',api.OperationAPI.as_view()),
    path('api/stock/',api.StockAPI.as_view()),
    path('api/blocks/<int:pk>/label/',api.BlockLabelAPI.as_view()),
    path('api/reports/<str:name>/',api.ReportsAPI.as_view()),
    path('api/bank-entries/',api.BankEntriesAPI.as_view()),
    path('api/export/<str:name>/',api.ExportAPI.as_view()),
    path('api/audit/',api.AuditAPI.as_view()),
    path('api/attachments/',api.AttachmentAPI.as_view()),
    path('api/attachments/<int:pk>/',api.AttachmentAPI.as_view()),
    path('api/security/<str:action>/',api.SecurityAPI.as_view()),
    path('api/health/',api.HealthAPI.as_view()),
    path('api/schema/',api.SchemaAPI.as_view()),
    path('api/import/<str:resource>/',api.ImportAPI.as_view()),
    path('api/approvals/',api.ApprovalsAPI.as_view()),
    path('api/approvals/<int:pk>/',api.ApprovalsAPI.as_view()),
    re_path(r'^(?!api/|admin/|static/)(?P<path>.*)$',shell),
]

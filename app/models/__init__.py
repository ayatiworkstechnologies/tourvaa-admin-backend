from app.models.roles import Role
from app.models.admin_modules import AdminModule
from app.models.permissions import Permission, RolePermission
from app.models.users import User
from app.models.settings import ApiSetting, AppSetting, PaymentSetting
from app.models.email_templates import EmailTemplate
from app.models.audit import AuditLog
from app.models.customers import Customer, CustomerCommunication, CustomerSavedTraveller, CustomerCancellationRequest, CustomerWishlistItem
from app.models.cms import Country, State, City, TourCategory, TourSubcategory, TourSubcategoryMap, Tour
from app.models.bookings import Booking, BookingTraveller, BookingOptionalActivity, BookingAccommodation, BookingExtension, BookingStatusHistory, BookingCommunication, MessageReply, EmailLog
from app.models.payments import Payment, PaymentTransaction, PaymentHold
from app.models.tours import (
    TourOverview, TourItinerary, TourInclusion, TourExclusion, TourHighlight,
    TourSimilar, TourExtension, TourGalleryImage,
    TourPricing, TourOptionalActivity, TourAccommodationExtra,
    TourCalendar, TourUnavailableDate, TourDiscount,
)
from app.models.suppliers import Supplier, SupplierApprovalHistory, SupplierContact, SupplierBusinessInfo, SupplierVehicle, SupplierInvoicing, SupplierDocument
from app.models.agents import Agent, AgentContact, AgentBusinessInfo, AgentInvoicing, AgentDocument
from app.models.affiliates import Affiliate, AffiliateMarketingInfo, AffiliateInvoicing, AffiliateDocument
from app.models.invoices import Invoice, InvoiceItem
from app.models.notifications import Notification, NotificationLog
from app.models.sessions import UserSession, LoginHistory
from app.models.chatbot import ChatFAQ, ChatSession, ChatMessage
from app.models.tour_versions import TourVersion, TourReviewComment
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.models.checkout import CheckoutSession
from app.models.website_cms import (
    HomepageBanner, PopularDestination, PopularTour, TourOnDeal,
    Blog, CustomerReview, HelpCentreArticle, CmsPolicy,
    PromotionalPopup, ExternalLink, SitemapEntry,
)
from app.models.cancellations import CancellationRequest, RefundRule
from app.models.reviews import TourReview
from app.models.booking_calendar import BookingCalendarEvent
from app.models.affiliate_tracking import (
    AffiliateLink,
    AffiliateClick,
    AffiliateAttribution,
    AffiliateCommissionRule,
    AffiliateConversion,
    AffiliatePayoutMethod,
    AffiliatePayout,
    AffiliatePayoutItem,
    AffiliateWalletTransaction,
)

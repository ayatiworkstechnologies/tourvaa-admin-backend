"""Provider-agnostic "external tours" layer (Day Tours & Experiences).

External inventory is displayed on Tourvaa but booked and paid for on the
provider's own site through an affiliate link. It never enters Tourvaa's
tours table, pricing, cart, checkout, bookings, invoices or payouts.
Viator is the only provider today; GetYourGuide/Klook would slot in as
another entry in PROVIDERS plus their own client/service/mapper package.
"""

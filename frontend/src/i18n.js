/** UI language: English (default) and Urdu (RTL).
 *
 *  `t(key, vars)` looks a key up in the active dictionary, falls back to
 *  English, and fills `{name}` placeholders from `vars`. When `vars.n === 1`
 *  and a `key_one` entry exists, that singular form is used.
 *
 *  Static markup opts in with attributes that `applyTranslations()` fills:
 *    data-i18n="key"              → textContent
 *    data-i18n-placeholder="key"  → placeholder
 *    data-i18n-title="key"        → title
 *    data-i18n-aria-label="key"   → aria-label
 *
 *  The choice is stored in localStorage as `rk_lang`; `?lang=ur|en` in the
 *  URL overrides it. Listing titles and descriptions come from Zameen.com in
 *  English and are left alone. Prices and phone numbers keep Western digits.
 */

import { refs } from './state.js';
import './rtl.css';

const LANG_KEY = 'rk_lang';
export const LANGS = ['en', 'ur'];

export const en = {
  'app.title': 'ZameenRentals — Find your rental in seconds',
  'app.description': "Map-first rental search across Karachi, Lahore, and Islamabad. Search in plain English or Roman Urdu — try 'DHA mein 2 bed flat 50k tak'.",
  'lang.switch': 'Switch language',
  'lang.toUrdu': 'Switch to Urdu',
  'lang.toEnglish': 'Switch to English',

  'offline.banner': "You're offline — showing cached data",
  'header.home': 'ZameenRentals home',
  'header.helpTitle': 'Help & examples',
  'header.helpAria': 'Help and search examples',
  'search.button': 'Search rentals',
  'search.trySearching': 'Try searching',
  'search.popular': 'Popular',
  'search.allListings': 'All listings',
  'header.alertsTitle': 'Get alerts for this search',
  'header.alertsLabel': 'Get alerts',
  'header.myRentals': 'My rentals',
  'header.myRentalsTitle': 'My rentals: new matches and saved homes',
  'header.myRentalsAria': 'My rentals: new matches, saved homes, viewed, and hidden listings',
  'header.clearAll': 'Clear All',

  'banner.text': 'Listings are sourced from Zameen.com and refreshed periodically — some may already be rented, so confirm with the agent before visiting. Spotted something off?',
  'banner.letUsKnow': 'Let us know',
  'common.dismiss': 'Dismiss',
  'common.close': 'Close',
  'common.cancel': 'Cancel',
  'common.apply': 'Apply',
  'common.any': 'Any',
  'common.custom': 'Custom',
  'common.optional': '(optional)',
  'common.loading': 'Loading…',
  'common.saving': 'Saving...',
  'common.failedLoad': 'Failed to load',

  'city.karachi': 'Karachi',
  'city.lahore': 'Lahore',
  'city.islamabad': 'Islamabad',

  'filter.nearMe': 'Near Me',
  'filter.area': 'Area',
  'filter.type': 'Type',
  'filter.beds': 'Beds',
  'filter.size': 'Size',
  'filter.price': 'Price',
  'filter.more': 'More',
  'filter.moreCount': 'More ({n})',
  'filter.selectArea': 'Select Area',
  'filter.areaPlaceholder': 'Type area name...',
  'filter.clearAreaSearch': 'Clear area search',
  'filter.noAreas': 'No areas found',
  'filter.propertyType': 'Property Type',
  'filter.bedrooms': 'Bedrooms',
  'filter.nearbyRadius': 'Nearby Radius',
  'filter.priceRange': 'Price Range',
  'filter.minPkr': 'Min (PKR)',
  'filter.maxPkr': 'Max (PKR)',
  'filter.propertySize': 'Property Size',
  'filter.sizeUnit': 'Size unit',
  'filter.minUnit': 'Min ({unit})',
  'filter.maxUnit': 'Max ({unit})',
  'filter.moreFilters': 'More Filters',
  'filter.furnishing': 'Furnishing',
  'filter.sortBy': 'Sort By',
  'filter.quickPresets': 'Quick Presets',

  'type.house': 'House',
  'type.apartment': 'Apartment',
  'type.upper_portion': 'Upper Portion',
  'type.lower_portion': 'Lower Portion',
  'type.room': 'Room',
  'type.penthouse': 'Penthouse',
  'type.farm_house': 'Farm House',

  'furnishing.furnished': 'Furnished',
  'furnishing.unfurnished': 'Unfurnished',

  'sort.default': 'Default',
  'sort.distance': 'Distance: Nearest',
  'sort.priceLow': 'Price: Low to High',
  'sort.priceHigh': 'Price: High to Low',
  'sort.newest': 'Newest First',

  'preset.budget1br': 'Budget 1BR',
  'preset.familyHome': 'Family Home',
  'preset.luxuryFlat': 'Luxury Flat',
  'preset.studioRoom': 'Studio/Room',

  'price.under30': 'Under 30K',
  'price.30to60': '30-60K',
  'price.60to100': '60-100K',
  'price.100to200': '100-200K',
  'price.200plus': '200K+',
  'price.onRequest': 'Price on request',

  'unit.km': '{n} km',
  'unit.marla': 'Marla',
  'unit.sqyd': 'Sq Yd',
  'size.marla': '{v} Marla',
  'size.kanal': '{v} Kanal',
  'size.sqyd': '{v} sq yd',
  'size.rangeMarla': '{a}–{b} Marla',
  'size.rangeSqyd': '{a}–{b} sq yd',
  'size.upTo': '≤ {v}',
  'size.plus': '{v}+',
  'size.sqydPlus': '{v}+ sq yd',
  'size.hintMarla': '1 Kanal = 20 Marla',
  'size.hintSqyd': '1 Marla ≈ 25 sq yd',

  'chip.bed': '{n} Bed',
  'chip.bedPlus': '{n}+ Bed',
  'chip.bedRange': '{a}-{b} Bed',
  'chip.priceRange': '{a}-{b}',
  'chip.priceMax': '<{v}',
  'chip.priceMin': '{v}+',

  'results.noResults': 'No results',
  'results.zeroShown': '0 shown',
  'results.showingRange': 'Showing 1–{shown} of {total}',
  'results.showingAll': 'Showing all {n}',
  'title.nearby': 'Rentals near you',
  'title.viewport': 'Rentals in this map view',
  'title.in': 'Rentals in {place}',
  'meta.default': 'Browse the map or use filters to refine results',
  'meta.withinKm': 'Within {km} km',
  'meta.noExactWithinKm': 'No exact-pin rentals found within {km} km',
  'meta.exactVisible': '{n} exact-pin rentals currently visible on the map',
  'meta.noExactVisible': 'No exact-pin rentals are visible in this map view',
  'meta.noExactHere': 'No exact-pin rentals visible here. {msg}',
  'meta.noExactInView': 'No exact-pin rentals are visible in this map view. {msg}',
  'meta.inArea': 'In this area',
  'meta.noneInArea': 'No rentals match this area right now',
  'meta.acrossFilters': 'Across current filters',
  'meta.noneInCity': 'No rentals match your filters in {city}',
  'rank.nearby': 'Nearby',
  'rank.newest': 'Newest first',
  'rank.lowest': 'Lowest price',
  'rank.highest': 'Highest price',
  'rank.nearest': 'Nearest first',
  'source.instant': 'Instant',
  'source.instantWith': 'Instant / {r}',
  'source.live': 'Live',
  'source.unavailable': 'No live results',
  'footer.powered': 'Powered by Zameen.com data',
  'data.updated': 'Data updated {rel}',
  'data.updatedStale': 'Data last updated {rel} — listings may have changed',

  'cov.acrossAll': '{total} across {covered} areas in view',
  'cov.acrossSome': '{total} across {covered} of {visible} areas in view',
  'cov.noneInVisible': 'No listings in the {n} areas in view yet',
  'cov.moveMap': 'Move the map to explore nearby areas',
  'cov.noAreasYet': 'No areas with listings here yet',
  'cov.summary': '{covered} of {visible} areas have listings',
  'cov.summaryNone': '{n} areas in view, none with listings yet',
  'cov.previewing': 'Previewing {area}. Grey areas are preview-only until listings are available there.',
  'cov.detailSome': 'Green areas have listings; grey are preview-only. Cards are ordered nearest to the map center.',
  'cov.detailNone': 'No listings in this part of the map yet. Grey areas are preview-only.',
  'cov.legend': 'Map legend',
  'cov.green': 'Green: has listings',
  'cov.grey': 'Grey: preview only',
  'cov.red': 'Red: exact listing',
  'cov.areasOnMap': 'Areas on map',
  'cov.openAreas': 'Open areas on map',
  'cov.areas': 'Areas',

  'empty.title': 'No rentals found',
  'empty.remove': 'Remove {label}',
  'empty.areaLabel': 'Area: {v}',
  'empty.typeLabel': 'Type: {v}',
  'empty.priceRange': 'Price range',
  'empty.tryRemoving': 'Try removing a filter to see more results',
  'empty.nearbyNone': 'No exact-pin rentals were found within {km} km.',
  'empty.exactZoomOut': 'No exact-pin rentals are visible here right now. Zoom out to broaden the map view.',
  'empty.exactPan': 'No exact-pin rentals are visible here right now. Pan or zoom the map to find nearby areas with listings.',
  'empty.exactNone': 'No exact-pin rentals are visible in this map view.',
  'empty.pan': 'Pan or zoom the map to discover other areas',

  'more.nearby': 'Load More Nearby Results',
  'more.view': 'Load More From This View',
  'more.results': 'Load More Results',
  'loading.more': 'Loading more...',

  'err.mapSearch': 'Map search failed',
  'err.search': 'Search failed',
  'err.nearby': 'Nearby search failed',
  'err.loadMore': 'Could not load more results.',
  'err.mapView': 'Could not update the map view right now',

  'toast.browseMode': 'Returned to browse mode.',
  'toast.setLocation': 'Set your location first to search nearby.',
  'toast.nearbyUnavailable': 'Nearby search is not available for this city.',
  'toast.nearMeRange': "Near Me covers Karachi, Lahore and Islamabad. You're about {km} km from {city}.",
  'toast.compareRemoved': 'Removed from compare',
  'toast.compareAdded': 'Added to compare ({n}/4)',
  'toast.compareNow': 'Compare now',
  'toast.favRemoved': 'Removed from favorites',
  'toast.favSaved': 'Saved to favorites',
  'toast.favError': 'Could not update favorite',
  'toast.hidden': "Hidden — it won't appear in your results",
  'toast.viewHidden': 'View hidden',
  'toast.hideError': 'Could not hide listing',
  'toast.actionFailed': 'Action failed',
  'toast.feedbackThanks': 'Thanks for your feedback!',
  'toast.feedbackQueued': 'You are offline. Feedback queued for delivery.',
  'toast.feedbackError': 'Could not send feedback. Please try again.',

  'nl.parsing': 'Parsing filters...',
  'nl.didYouMean': 'Did you mean:',
  'nl.notUnderstood': 'Could not understand. Try "{ex}"',
  'nl.notUnderstoodExample': '2 bed flat in DHA under 50k',
  'nl.error': 'Something went wrong.',
  'nl.understood': 'Understood:',
  'nl.approx': 'No exact match for “{q}” — showing {area}',
  'nl.removeFilter': 'Remove {label} filter',
  'understood.beds': '{n} bed',
  'understood.bedsRange': '{a}–{b} bed',
  'understood.priceRange': '{a}–{b}',
  'understood.under': 'Under {v}',
  'understood.plus': '{v}+',

  'feedback.btn': 'Feedback',
  'feedback.btnTitle': 'Send feedback',
  'feedback.title': 'Send Feedback',
  'feedback.close': 'Close feedback',
  'feedback.placeholder': "What's wrong? What could be better?",
  'feedback.context': 'Your current search context is attached automatically.',
  'feedback.send': 'Send',
  'feedback.sending': 'Sending...',

  'map.show': 'Show map',
  'map.showList': 'Show list',
  'map.street': 'Street',
  'map.satellite': 'Satellite',
  'map.centerMe': 'Center on my location',
  'map.useLocation': 'Use my location',
  'geo.error': 'Could not get your location right now.',
  'geo.denied': 'Location permission was denied.',
  'geo.unavailable': 'Your location is unavailable right now.',
  'geo.timeout': 'Getting your location timed out.',
  'geo.unsupported': 'Your browser does not support location services.',

  'drawer.close': 'Close listing details',
  'gallery.close': 'Close gallery',
  'gallery.prev': 'Previous photo',
  'gallery.next': 'Next photo',
  'install.msg': 'Add ZameenRentals to your home screen for faster access',
  'install.ios': 'Tap Share then "Add to Home Screen" for faster access',
  'install.btn': 'Install',
  'install.dismiss': 'Dismiss install prompt',

  'card.bed': '{n} bed',
  'card.bath': '{n} bath',
  'card.new': 'New',
  'card.perMonth': '/mo',
  'card.untitled': 'Rental Property',
  'card.repost': 'Listed {n}×',
  'card.repostTitle': 'The same listing was posted {n} times by agents — showing it once',
  'card.repostAria': 'Listed {n} times',
  'card.added': 'Added {rel}',
  'card.updated': 'Updated {rel}',
  'card.hideTitle': "Hide this listing — it won't show up in your results",
  'card.hideAria': 'Hide this listing',
  'card.openZameen': 'Open on Zameen.com',
  'fav.remove': 'Remove from favorites',
  'fav.save': 'Save to favorites',
  'compare.remove': 'Remove from compare',
  'compare.add': 'Add to compare',
  'contact.call': 'Call',
  'contact.whatsapp': 'WhatsApp',
  'contact.waMessage': 'Salaam, is this property still available? ',
  'distance.m': '{n} m away',
  'distance.km': '{n} km away',
  'distance.approx': '~',

  'drawer.photo': '{n} photo',
  'drawer.photos': '{n} photos',
  'drawer.bedrooms_one': '{n} bedroom',
  'drawer.bedrooms': '{n} bedrooms',
  'drawer.bathrooms_one': '{n} bathroom',
  'drawer.bathrooms': '{n} bathrooms',
  'drawer.nearbyAreas': 'Nearby areas',
  'drawer.saved': 'Saved',
  'drawer.save': 'Save',
  'drawer.hide': 'Hide',
  'drawer.hideTitle': "Hide this listing — it won't show up in your future search results",
  'drawer.inCompare': 'In compare',
  'drawer.compare': 'Compare',
  'drawer.inCompareList': 'In compare list',
  'drawer.forRent': '{type} for Rent',
  'drawer.perMonthSlash': '/ month',
  'drawer.perMonth': 'per month',
  'drawer.location': 'Location',
  'drawer.exactPin': 'Exact listing pin',
  'drawer.approxPin': 'Approximate area location',
  'drawer.viewZameen': 'View on Zameen.com',
  'drawer.about': 'About this property',
  'drawer.showMore': 'Show more',
  'drawer.showLess': 'Show less',
  'drawer.offers': 'What this place offers',
  'drawer.showAllAmenities': 'Show all {n} amenities',
  'drawer.propertyDetails': 'Property details',
  'drawer.details': 'Details',
  'drawer.loadError': 'Could not load details',

  'compare.already': 'Already in compare',
  'compare.max': 'You can compare up to {n} listings at a time.',
  'compare.trayAria': 'Compare listings tray',
  'compare.listing': 'Listing',
  'compare.clearList': 'Clear compare list',
  'compare.selected': 'Compare selected listings',
  'compare.needTwo': 'Add at least 2 listings to compare',
  'compare.trayBtn': 'Compare {n}/{max}',
  'compare.sizeApprox': '{size} (≈{m} marla)',
  'compare.thisListing': 'This listing',
  'compare.onlyDiff': 'Only differences',
  'compare.title': 'Compare ({n})',
  'compare.clearAll': 'Clear all',
  'compare.bestValue': 'Best value:',
  'compare.perMarla': '{v}/marla',
  'compare.same': 'Same',
  'compare.secValue': 'Value',
  'compare.secSpace': 'Space',
  'compare.secLocation': 'Location',
  'compare.secFreshness': 'Freshness',
  'compare.secContact': 'Contact',
  'compare.rsMarla': 'Rs / marla',
  'compare.rsBed': 'Rs / bedroom',
  'compare.price': 'Price',
  'compare.bedrooms': 'Bedrooms',
  'compare.bathrooms': 'Bathrooms',
  'compare.size': 'Size',
  'compare.type': 'Type',
  'compare.area': 'Area',
  'compare.distance': 'Distance',
  'compare.posted': 'Posted',
  'compare.phone': 'Phone / WhatsApp',
  'compare.badgeBest': 'Best value',
  'compare.badgePerRoom': 'Per room',
  'compare.badgeLowest': 'Lowest',
  'compare.badgeClosest': 'Closest',
  'compare.badgeNewest': 'Newest',
  'compare.available': 'Available',
  'compare.notYet': 'Not yet',
  'compare.viewDetails': 'View details',

  'ptab.alerts': 'New matches',
  'ptab.favorites': 'Saved homes',
  'ptab.recent': 'Viewed',
  'ptab.hidden': 'Hidden',
  'panel.subtitle': 'Your alerts and saved homes',
  'alerts.dialogTitle': 'Get alerts for new rentals',
  'alerts.dialogBody': "We'll keep watching this search and show you new matches as they arrive.",
  'alerts.watchingFor': 'Watching for:',
  'alerts.allNew': 'All new rentals',
  'alerts.nameLabel': 'Name this alert',
  'alerts.newRentals': 'New rentals',
  'alerts.findUpdates': "You'll find updates in {strong}. You can also turn on device notifications after saving.",
  'alerts.start': 'Start alert',
  'alerts.save': 'Save alert',
  'alerts.forThisSearch': '+ Alert for this search',
  'alerts.createTitle': 'Create an alert for the search you are viewing',
  'alerts.chooseFirst': 'Choose filters first, then create an alert',
  'alerts.noneYet': 'No alerts yet',
  'alerts.neverMiss': 'Never miss a matching rental',
  'alerts.howTo': 'Choose your city and filters, then create an alert for that search. New matches will collect here automatically.',
  'alerts.yours': 'Your alerts ({n})',
  'alerts.allRentals': 'All rentals',
  'alerts.newCount': '{n} new',
  'alerts.noMatches': "No matches yet — we're watching.",
  'alerts.paused': 'Paused',
  'alerts.resume': 'Resume',
  'alerts.pause': 'Pause',
  'alerts.delete': 'Delete',
  'alerts.confirmDelete': 'Delete this alert?',
  'summary.beds': '{n} bed',
  'summary.bedsRange': '{a}-{b} bed',
  'summary.in': 'in {place}',
  'summary.range': '{a}K–{b}K PKR',
  'summary.under': 'under {v}K PKR',
  'summary.over': 'over {v}K PKR',
  'summary.furnished': 'furnished',
  'summary.unfurnished': 'unfurnished',
  'push.unsupported': "Device notifications aren't available in this browser. New matches will still appear here.",
  'push.blocked': 'Device notifications are blocked in your browser settings. New matches will still appear here.',
  'push.ask': 'Want a heads-up when a new rental matches?',
  'push.notifyMe': 'Notify me',
  'push.reconnectMsg': 'Notifications need one quick reconnect on this device.',
  'push.reconnect': 'Reconnect',
  'push.on': 'Notifications are on for this device.',
  'push.test': 'Test',
  'push.turnOff': 'Turn off',
  'push.requesting': 'Requesting…',
  'toast.alertSaved': "Alert saved. We'll watch for new matches.",
  'toast.alertError': 'Could not save alert.',
  'toast.alertDeleted': 'Alert deleted.',
  'toast.deleteFailed': 'Delete failed',
  'toast.updateFailed': 'Update failed',
  'toast.pushEnabled': 'Push notifications enabled.',
  'toast.pushDenied': 'Push notifications denied.',
  'toast.pushError': 'Could not enable push notifications.',
  'toast.testSent': 'Test push sent to {n} device(s).',
  'toast.noSubs': 'No push subscriptions found.',
  'toast.testFailed': 'Test push failed',
  'toast.pushOff': 'Device notifications turned off.',
  'toast.pushOffError': 'Could not turn off notifications.',
  'toast.favRemovedDot': 'Removed from favorites.',
  'toast.unhidden': 'Unhidden.',
  'fav.emptyTitle': 'No saved listings yet',
  'fav.emptyBody': 'Tap the heart on any listing to save it for later.',
  'fav.count': 'Saved ({n})',
  'hidden.emptyTitle': 'No hidden listings',
  'hidden.emptyBody': "Hide listings you're not interested in to clean up your results.",
  'hidden.count': 'Hidden ({n})',
  'recent.emptyTitle': 'Nothing viewed yet',
  'recent.emptyBody': 'Listings you open will show up here for quick re-access.',
  'recent.count': 'Recently viewed ({n})',
  'saved.rental': 'Rental',
  'saved.savedAgo': 'saved {rel}',
  'saved.hiddenAgo': 'hidden {rel}',
  'saved.open': 'Open',
  'saved.unhide': 'Unhide',
  'saved.remove': 'Remove',

  'welcome.question': 'What are you looking for in {city}?',
  'welcome.seeTips': 'See tips',
  'welcome.dismissAria': 'Dismiss getting-started guide',
  'welcome.browse': 'Browse fresh {city} rentals',
  'welcome.title': 'How to find your rental',
  'welcome.body': 'Search in plain English or Roman Urdu, pick a starter below, or just browse the freshest listings.',
  'welcome.searchingIn': 'Searching in',
  'welcome.orTry': 'Or try a search',
  'welcome.tour': 'Take a quick tour',
  'welcome.skip': 'Skip',

  'tour.searchTitle': 'Search in plain words',
  'tour.searchBody': 'Type what you want — “2 bed flat DHA under 50k” or “DHA mein 2 bed flat 50k tak”. We pull out the area, type, beds and budget for you.',
  'tour.cityTitle': 'Pick your city',
  'tour.cityBody': 'Switch between Lahore, Karachi and Islamabad. Each city reloads its areas and re-centres the map.',
  'tour.filtersTitle': 'Refine with filters',
  'tour.filtersBody': 'Narrow by area, type, beds and price — or tap Near Me to search around your location.',
  'tour.compareTitle': 'Compare homes side by side',
  'tour.compareBody': 'Tap the compare icon on any listing to add it to your tray, then see up to four homes in one table — best value per marla, distance, freshness and more.',
  'tour.alertsTitle': 'Save homes & get alerts',
  'tour.alertsBody': 'Open “My rentals” for your saved favourites, recently viewed listings, and alerts when new matches appear.',
  'tour.mapTitle': 'Explore on the map',
  'tour.mapBody': 'Browse by neighbourhood — green dots are areas with listings, red pins are exact addresses.',
  'tour.helpTitle': 'Help is always here',
  'tour.helpBody': 'Tap the help button anytime to reopen tips, search examples and this tour.',
  'tour.progress': '{{current}} of {{total}}',
  'tour.next': 'Next',
  'tour.back': 'Back',
  'tour.done': 'Got it',

  'voice.blocked': 'Microphone access is blocked. Allow it in your browser settings to search by voice.',
  'voice.noMic': 'No microphone found.',
  'voice.cantStart': 'Could not start the microphone.',
  'voice.stop': 'Stop recording',
  'voice.search': 'Search by voice',
  'voice.transcribing': 'Transcribing...',
  'voice.transcribeError': 'Could not transcribe. Please try again.',
  'voice.didntCatch': "Didn't catch that. Tap the mic and try again.",
  'voice.recordFailed': 'Recording failed. Tap the mic and try again.',
  'voice.recordStartFailed': 'Could not start recording. Tap the mic and try again.',
  'voice.listening': 'Listening...',
  'voice.tapStop': ' · tap to stop',

  'sw.updated': 'App updated. Refresh for the latest version.',
  'sw.refresh': 'Refresh',
  'sw.queuedSent': 'Queued feedback sent successfully.',

  'time.justNow': 'just now',
  'time.minutes_one': '{n} minute ago',
  'time.minutes': '{n} minutes ago',
  'time.hours_one': '{n} hour ago',
  'time.hours': '{n} hours ago',
  'time.days_one': '{n} day ago',
  'time.days': '{n} days ago',
  'time.weeks_one': '{n} week ago',
  'time.weeks': '{n} weeks ago',
  'time.months_one': '{n} month ago',
  'time.months': '{n} months ago',
  'time.years_one': '{n} year ago',
  'time.years': '{n} years ago',
};

// Everyday Pakistani Urdu: loanwords people actually say (فلیٹ، پورشن، بیڈ،
// الرٹ، فلٹر) over formal coinages. Digits stay Western.
export const ur = {
  'app.title': 'زمین رینٹلز — کرائے کا گھر سیکنڈوں میں ڈھونڈیں',
  'app.description': 'کراچی، لاہور اور اسلام آباد میں نقشے پر کرائے کے گھر تلاش کریں۔ اردو، رومن اردو یا انگریزی میں لکھیں — جیسے "ڈی ایچ اے میں 2 بیڈ فلیٹ 50 ہزار تک"۔',
  'lang.switch': 'زبان تبدیل کریں',
  'lang.toUrdu': 'اردو میں دیکھیں',
  'lang.toEnglish': 'انگریزی میں دیکھیں',

  'offline.banner': 'آپ آف لائن ہیں — محفوظ شدہ ڈیٹا دکھایا جا رہا ہے',
  'header.home': 'زمین رینٹلز ہوم',
  'header.helpTitle': 'مدد اور مثالیں',
  'header.helpAria': 'مدد اور تلاش کی مثالیں',
  'search.button': 'تلاش کریں',
  'search.trySearching': 'ایسے تلاش کریں',
  'search.popular': 'مقبول تلاشیں',
  'search.allListings': 'تمام اشتہارات',
  'header.alertsTitle': 'اس تلاش کے الرٹس حاصل کریں',
  'header.alertsLabel': 'الرٹ لگائیں',
  'header.myRentals': 'میری فہرست',
  'header.myRentalsTitle': 'میری فہرست: نئے میچ اور محفوظ گھر',
  'header.myRentalsAria': 'میری فہرست: نئے میچ، محفوظ گھر، دیکھے گئے اور چھپائے گئے اشتہارات',
  'header.clearAll': 'سب صاف کریں',

  'banner.text': 'یہ اشتہارات Zameen.com سے لیے جاتے ہیں اور وقتاً فوقتاً اپڈیٹ ہوتے ہیں — کچھ گھر شاید کرائے پر جا چکے ہوں، اس لیے جانے سے پہلے ایجنٹ سے تصدیق کر لیں۔ کچھ غلط نظر آیا؟',
  'banner.letUsKnow': 'ہمیں بتائیں',
  'common.dismiss': 'بند کریں',
  'common.close': 'بند کریں',
  'common.cancel': 'منسوخ',
  'common.apply': 'لاگو کریں',
  'common.any': 'کوئی بھی',
  'common.custom': 'اپنی مرضی',
  'common.optional': '(اختیاری)',
  'common.loading': 'لوڈ ہو رہا ہے…',
  'common.saving': 'محفوظ ہو رہا ہے...',
  'common.failedLoad': 'لوڈ نہیں ہو سکا',

  'city.karachi': 'کراچی',
  'city.lahore': 'لاہور',
  'city.islamabad': 'اسلام آباد',

  'filter.nearMe': 'میرے قریب',
  'filter.area': 'علاقہ',
  'filter.type': 'قسم',
  'filter.beds': 'بیڈ روم',
  'filter.size': 'سائز',
  'filter.price': 'کرایہ',
  'filter.more': 'مزید',
  'filter.moreCount': 'مزید ({n})',
  'filter.selectArea': 'علاقہ منتخب کریں',
  'filter.areaPlaceholder': 'علاقے کا نام لکھیں...',
  'filter.clearAreaSearch': 'علاقے کی تلاش صاف کریں',
  'filter.noAreas': 'کوئی علاقہ نہیں ملا',
  'filter.propertyType': 'پراپرٹی کی قسم',
  'filter.bedrooms': 'بیڈ روم',
  'filter.nearbyRadius': 'کتنے فاصلے تک',
  'filter.priceRange': 'ماہانہ کرایہ',
  'filter.minPkr': 'کم از کم (روپے)',
  'filter.maxPkr': 'زیادہ سے زیادہ (روپے)',
  'filter.propertySize': 'پراپرٹی کا سائز',
  'filter.sizeUnit': 'پیمائش کی اکائی',
  'filter.minUnit': 'کم از کم ({unit})',
  'filter.maxUnit': 'زیادہ سے زیادہ ({unit})',
  'filter.moreFilters': 'مزید فلٹرز',
  'filter.furnishing': 'فرنیچر',
  'filter.sortBy': 'ترتیب',
  'filter.quickPresets': 'فوری انتخاب',

  'type.house': 'گھر',
  'type.apartment': 'فلیٹ',
  'type.upper_portion': 'اپر پورشن',
  'type.lower_portion': 'لوئر پورشن',
  'type.room': 'کمرہ',
  'type.penthouse': 'پینٹ ہاؤس',
  'type.farm_house': 'فارم ہاؤس',

  'furnishing.furnished': 'فرنشڈ',
  'furnishing.unfurnished': 'بغیر فرنیچر',

  'sort.default': 'عام ترتیب',
  'sort.distance': 'فاصلہ: قریب ترین پہلے',
  'sort.priceLow': 'کرایہ: کم سے زیادہ',
  'sort.priceHigh': 'کرایہ: زیادہ سے کم',
  'sort.newest': 'نئے اشتہار پہلے',

  'preset.budget1br': 'سستا 1 بیڈ',
  'preset.familyHome': 'فیملی گھر',
  'preset.luxuryFlat': 'لگژری فلیٹ',
  'preset.studioRoom': 'اسٹوڈیو / کمرہ',

  'price.under30': '30 ہزار سے کم',
  'price.30to60': '30 تا 60 ہزار',
  'price.60to100': '60 ہزار تا 1 لاکھ',
  'price.100to200': '1 تا 2 لاکھ',
  'price.200plus': '2 لاکھ سے زیادہ',
  'price.onRequest': 'کرایہ پوچھیں',

  'unit.km': '{n} کلومیٹر',
  'unit.marla': 'مرلہ',
  'unit.sqyd': 'گز',
  'size.marla': '{v} مرلہ',
  'size.kanal': '{v} کنال',
  'size.sqyd': '{v} گز',
  'size.rangeMarla': '{a} تا {b} مرلہ',
  'size.rangeSqyd': '{a} تا {b} گز',
  'size.upTo': '{v} تک',
  'size.plus': '{v} سے زیادہ',
  'size.sqydPlus': '{v} گز سے زیادہ',
  'size.hintMarla': '1 کنال = 20 مرلے',
  'size.hintSqyd': '1 مرلہ ≈ 25 گز',

  'chip.bed': '{n} بیڈ',
  'chip.bedPlus': '{n} یا زیادہ بیڈ',
  'chip.bedRange': '{a} تا {b} بیڈ',
  'chip.priceRange': '{a} تا {b}',
  'chip.priceMax': '{v} تک',
  'chip.priceMin': '{v} سے زیادہ',

  'results.noResults': 'کوئی نتیجہ نہیں',
  'results.zeroShown': '0 دکھائے گئے',
  'results.showingRange': '{total} میں سے {shown}',
  'results.showingAll': 'تمام {n} گھر',
  'title.nearby': 'آپ کے قریب کرائے کے گھر',
  'title.viewport': 'نقشے کے اس حصے میں کرائے کے گھر',
  'title.in': '{place} میں کرائے کے گھر',
  'meta.default': 'نقشہ دیکھیں یا فلٹرز سے نتائج کو محدود کریں',
  'meta.withinKm': '{km} کلومیٹر کے اندر',
  'meta.noExactWithinKm': '{km} کلومیٹر کے اندر درست مقام والا کوئی گھر نہیں ملا',
  'meta.exactVisible': 'نقشے پر درست مقام والے {n} گھر نظر آ رہے ہیں',
  'meta.noExactVisible': 'نقشے کے اس حصے میں درست مقام والا کوئی گھر نظر نہیں آ رہا',
  'meta.noExactHere': 'یہاں درست مقام والا کوئی گھر نظر نہیں آ رہا۔ {msg}',
  'meta.noExactInView': 'نقشے کے اس حصے میں درست مقام والا کوئی گھر نظر نہیں آ رہا۔ {msg}',
  'meta.inArea': 'اس علاقے میں',
  'meta.noneInArea': 'اس وقت اس علاقے میں کوئی گھر نہیں ملا',
  'meta.acrossFilters': 'موجودہ فلٹرز کے مطابق',
  'meta.noneInCity': '{city} میں آپ کے فلٹرز کے مطابق کوئی گھر نہیں ملا',
  'rank.nearby': 'قریب ترین',
  'rank.newest': 'نئے پہلے',
  'rank.lowest': 'کم کرایہ پہلے',
  'rank.highest': 'زیادہ کرایہ پہلے',
  'rank.nearest': 'قریب ترین پہلے',
  'source.instant': 'فوری',
  'source.instantWith': 'فوری / {r}',
  'source.live': 'لائیو',
  'source.unavailable': 'لائیو نتائج نہیں ملے',
  'footer.powered': 'ڈیٹا: Zameen.com',
  'data.updated': 'ڈیٹا {rel} اپڈیٹ ہوا',
  'data.updatedStale': 'ڈیٹا آخری بار {rel} اپڈیٹ ہوا — اشتہارات بدل چکے ہوں گے',

  'cov.acrossAll': 'نظر آنے والے {covered} علاقوں میں {total} گھر',
  'cov.acrossSome': 'نظر آنے والے {visible} میں سے {covered} علاقوں میں {total} گھر',
  'cov.noneInVisible': 'نظر آنے والے {n} علاقوں میں ابھی کوئی اشتہار نہیں',
  'cov.moveMap': 'قریبی علاقے دیکھنے کے لیے نقشہ ہلائیں',
  'cov.noAreasYet': 'یہاں ابھی کسی علاقے میں اشتہار نہیں',
  'cov.summary': '{visible} میں سے {covered} علاقوں میں اشتہار ہیں',
  'cov.summaryNone': 'نقشے پر {n} علاقے، کسی میں ابھی اشتہار نہیں',
  'cov.previewing': '{area} دیکھ رہے ہیں۔ سرمئی علاقوں میں اشتہار آنے تک صرف جھلک دکھائی جاتی ہے۔',
  'cov.detailSome': 'سبز علاقوں میں اشتہار ہیں، سرمئی صرف جھلک ہیں۔ کارڈز نقشے کے مرکز سے قریب ترین ترتیب میں ہیں۔',
  'cov.detailNone': 'نقشے کے اس حصے میں ابھی کوئی اشتہار نہیں۔ سرمئی علاقے صرف جھلک ہیں۔',
  'cov.legend': 'نقشے کی علامات',
  'cov.green': 'سبز: اشتہار موجود',
  'cov.grey': 'سرمئی: صرف جھلک',
  'cov.red': 'سرخ: درست مقام',
  'cov.areasOnMap': 'نقشے پر علاقے',
  'cov.openAreas': 'نقشے پر علاقے کھولیں',
  'cov.areas': 'علاقے',

  'empty.title': 'کوئی گھر نہیں ملا',
  'empty.remove': '{label} ہٹائیں',
  'empty.areaLabel': 'علاقہ: {v}',
  'empty.typeLabel': 'قسم: {v}',
  'empty.priceRange': 'کرایے کی حد',
  'empty.tryRemoving': 'مزید نتائج کے لیے کوئی فلٹر ہٹا کر دیکھیں',
  'empty.nearbyNone': '{km} کلومیٹر کے اندر درست مقام والا کوئی گھر نہیں ملا۔',
  'empty.exactZoomOut': 'اس وقت یہاں درست مقام والا کوئی گھر نظر نہیں آ رہا۔ نقشہ چھوٹا کر کے بڑا حصہ دیکھیں۔',
  'empty.exactPan': 'اس وقت یہاں درست مقام والا کوئی گھر نظر نہیں آ رہا۔ نقشہ ہلا کر یا زوم کر کے قریبی علاقے دیکھیں۔',
  'empty.exactNone': 'نقشے کے اس حصے میں درست مقام والا کوئی گھر نظر نہیں آ رہا۔',
  'empty.pan': 'دوسرے علاقے دیکھنے کے لیے نقشہ ہلائیں یا زوم کریں',

  'more.nearby': 'مزید قریبی گھر دیکھیں',
  'more.view': 'اس حصے سے مزید گھر دیکھیں',
  'more.results': 'مزید گھر دیکھیں',
  'loading.more': 'مزید لوڈ ہو رہے ہیں...',

  'err.mapSearch': 'نقشے پر تلاش نہیں ہو سکی',
  'err.search': 'تلاش نہیں ہو سکی',
  'err.nearby': 'قریبی تلاش نہیں ہو سکی',
  'err.loadMore': 'مزید نتائج لوڈ نہیں ہو سکے۔',
  'err.mapView': 'اس وقت نقشہ اپڈیٹ نہیں ہو سکا',

  'toast.browseMode': 'عام تلاش پر واپس آ گئے۔',
  'toast.setLocation': 'قریبی تلاش کے لیے پہلے اپنا مقام دیں۔',
  'toast.nearbyUnavailable': 'اس شہر میں قریبی تلاش دستیاب نہیں۔',
  'toast.nearMeRange': '"میرے قریب" صرف کراچی، لاہور اور اسلام آباد میں کام کرتا ہے۔ آپ {city} سے تقریباً {km} کلومیٹر دور ہیں۔',
  'toast.compareRemoved': 'موازنے سے ہٹا دیا',
  'toast.compareAdded': 'موازنے میں شامل ({n}/4)',
  'toast.compareNow': 'ابھی موازنہ کریں',
  'toast.favRemoved': 'پسندیدہ سے ہٹا دیا',
  'toast.favSaved': 'پسندیدہ میں محفوظ ہو گیا',
  'toast.favError': 'پسندیدہ اپڈیٹ نہیں ہو سکا',
  'toast.hidden': 'چھپا دیا — یہ آپ کے نتائج میں نظر نہیں آئے گا',
  'toast.viewHidden': 'چھپائے گئے دیکھیں',
  'toast.hideError': 'اشتہار چھپایا نہیں جا سکا',
  'toast.actionFailed': 'یہ کام نہیں ہو سکا',
  'toast.feedbackThanks': 'آپ کی رائے کا شکریہ!',
  'toast.feedbackQueued': 'آپ آف لائن ہیں۔ رائے انٹرنیٹ آنے پر بھیج دی جائے گی۔',
  'toast.feedbackError': 'رائے نہیں بھیجی جا سکی۔ دوبارہ کوشش کریں۔',

  'nl.parsing': 'آپ کی تلاش سمجھی جا رہی ہے...',
  'nl.didYouMean': 'کیا آپ کا مطلب تھا:',
  'nl.notUnderstood': 'سمجھ نہیں آیا۔ ایسے لکھ کر دیکھیں: "{ex}"',
  'nl.notUnderstoodExample': 'ڈی ایچ اے میں 2 بیڈ فلیٹ 50 ہزار تک',
  'nl.error': 'کچھ گڑبڑ ہو گئی۔',
  'nl.understood': 'ہم سمجھے:',
  'nl.approx': '“{q}” سے بالکل میل نہیں ملا — {area} دکھا رہے ہیں',
  'nl.removeFilter': '{label} فلٹر ہٹائیں',
  'understood.beds': '{n} بیڈ',
  'understood.bedsRange': '{a} تا {b} بیڈ',
  'understood.priceRange': '{a} تا {b}',
  'understood.under': '{v} تک',
  'understood.plus': '{v} سے زیادہ',

  'feedback.btn': 'رائے دیں',
  'feedback.btnTitle': 'اپنی رائے بھیجیں',
  'feedback.title': 'اپنی رائے بھیجیں',
  'feedback.close': 'رائے کا خانہ بند کریں',
  'feedback.placeholder': 'کیا مسئلہ ہے؟ کیا بہتر ہو سکتا ہے؟',
  'feedback.context': 'آپ کی موجودہ تلاش کی تفصیل خود بخود ساتھ بھیجی جاتی ہے۔',
  'feedback.send': 'بھیجیں',
  'feedback.sending': 'بھیجا جا رہا ہے...',

  'map.show': 'نقشہ دکھائیں',
  'map.showList': 'فہرست دکھائیں',
  'map.street': 'سڑکیں',
  'map.satellite': 'سیٹلائٹ',
  'map.centerMe': 'میرے مقام پر لے جائیں',
  'map.useLocation': 'میرا مقام استعمال کریں',
  'geo.error': 'اس وقت آپ کا مقام معلوم نہیں ہو سکا۔',
  'geo.denied': 'مقام کی اجازت نہیں دی گئی۔',
  'geo.unavailable': 'اس وقت آپ کا مقام دستیاب نہیں۔',
  'geo.timeout': 'مقام معلوم کرنے میں بہت دیر لگ گئی۔',
  'geo.unsupported': 'آپ کا براؤزر لوکیشن سروس سپورٹ نہیں کرتا۔',

  'drawer.close': 'تفصیلات بند کریں',
  'gallery.close': 'تصاویر بند کریں',
  'gallery.prev': 'پچھلی تصویر',
  'gallery.next': 'اگلی تصویر',
  'install.msg': 'جلد رسائی کے لیے زمین رینٹلز کو اپنی ہوم اسکرین پر لگائیں',
  'install.ios': 'جلد رسائی کے لیے Share دبائیں، پھر "Add to Home Screen" چنیں',
  'install.btn': 'انسٹال کریں',
  'install.dismiss': 'انسٹال کا پیغام بند کریں',

  'card.bed': '{n} بیڈ',
  'card.bath': '{n} باتھ',
  'card.new': 'نیا',
  'card.perMonth': '/ ماہ',
  'card.untitled': 'کرائے کی پراپرٹی',
  'card.repost': '{n} بار لگا',
  'card.repostTitle': 'ایجنٹوں نے یہ اشتہار {n} بار لگایا — یہاں ایک ہی بار دکھایا گیا ہے',
  'card.repostAria': '{n} بار لگایا گیا',
  'card.added': '{rel} لگایا گیا',
  'card.updated': '{rel} اپڈیٹ ہوا',
  'card.hideTitle': 'یہ اشتہار چھپائیں — یہ آپ کے نتائج میں نظر نہیں آئے گا',
  'card.hideAria': 'یہ اشتہار چھپائیں',
  'card.openZameen': 'Zameen.com پر کھولیں',
  'fav.remove': 'پسندیدہ سے ہٹائیں',
  'fav.save': 'پسندیدہ میں محفوظ کریں',
  'compare.remove': 'موازنے سے ہٹائیں',
  'compare.add': 'موازنے میں شامل کریں',
  'contact.call': 'کال کریں',
  'contact.whatsapp': 'واٹس ایپ',
  'contact.waMessage': 'السلام علیکم، کیا یہ پراپرٹی ابھی دستیاب ہے؟ ',
  'distance.m': '{n} میٹر دور',
  'distance.km': '{n} کلومیٹر دور',
  'distance.approx': 'تقریباً ',

  'drawer.photo': '{n} تصویر',
  'drawer.photos': '{n} تصاویر',
  'drawer.bedrooms': '{n} بیڈ روم',
  'drawer.bathrooms': '{n} باتھ روم',
  'drawer.nearbyAreas': 'قریبی علاقے',
  'drawer.saved': 'محفوظ',
  'drawer.save': 'محفوظ کریں',
  'drawer.hide': 'چھپائیں',
  'drawer.hideTitle': 'یہ اشتہار چھپائیں — یہ آپ کی آئندہ تلاش میں نظر نہیں آئے گا',
  'drawer.inCompare': 'موازنے میں',
  'drawer.compare': 'موازنہ',
  'drawer.inCompareList': 'موازنے کی فہرست میں',
  'drawer.forRent': '{type} کرائے کے لیے',
  'drawer.perMonthSlash': '/ ماہ',
  'drawer.perMonth': 'ماہانہ',
  'drawer.location': 'مقام',
  'drawer.exactPin': 'اشتہار کا درست مقام',
  'drawer.approxPin': 'علاقے کا اندازاً مقام',
  'drawer.viewZameen': 'Zameen.com پر دیکھیں',
  'drawer.about': 'اس پراپرٹی کے بارے میں',
  'drawer.showMore': 'مزید پڑھیں',
  'drawer.showLess': 'کم دکھائیں',
  'drawer.offers': 'سہولیات',
  'drawer.showAllAmenities': 'تمام {n} سہولیات دکھائیں',
  'drawer.propertyDetails': 'پراپرٹی کی تفصیل',
  'drawer.details': 'تفصیلات',
  'drawer.loadError': 'تفصیلات لوڈ نہیں ہو سکیں',

  'compare.already': 'یہ پہلے ہی موازنے میں ہے',
  'compare.max': 'ایک وقت میں زیادہ سے زیادہ {n} اشتہارات کا موازنہ ہو سکتا ہے۔',
  'compare.trayAria': 'موازنے کی ٹرے',
  'compare.listing': 'اشتہار',
  'compare.clearList': 'موازنے کی فہرست صاف کریں',
  'compare.selected': 'منتخب اشتہارات کا موازنہ کریں',
  'compare.needTwo': 'موازنے کے لیے کم از کم 2 اشتہار شامل کریں',
  'compare.trayBtn': 'موازنہ {n}/{max}',
  'compare.sizeApprox': '{size} (≈{m} مرلہ)',
  'compare.thisListing': 'یہ اشتہار',
  'compare.onlyDiff': 'صرف فرق',
  'compare.title': 'موازنہ ({n})',
  'compare.clearAll': 'سب ہٹائیں',
  'compare.bestValue': 'سب سے اچھا سودا:',
  'compare.perMarla': '{v} فی مرلہ',
  'compare.same': 'یکساں',
  'compare.secValue': 'قیمت',
  'compare.secSpace': 'جگہ',
  'compare.secLocation': 'مقام',
  'compare.secFreshness': 'تازگی',
  'compare.secContact': 'رابطہ',
  'compare.rsMarla': 'روپے فی مرلہ',
  'compare.rsBed': 'روپے فی بیڈ روم',
  'compare.price': 'کرایہ',
  'compare.bedrooms': 'بیڈ روم',
  'compare.bathrooms': 'باتھ روم',
  'compare.size': 'سائز',
  'compare.type': 'قسم',
  'compare.area': 'علاقہ',
  'compare.distance': 'فاصلہ',
  'compare.posted': 'لگایا گیا',
  'compare.phone': 'فون / واٹس ایپ',
  'compare.badgeBest': 'اچھا سودا',
  'compare.badgePerRoom': 'فی کمرہ',
  'compare.badgeLowest': 'سب سے کم',
  'compare.badgeClosest': 'قریب ترین',
  'compare.badgeNewest': 'تازہ ترین',
  'compare.available': 'دستیاب',
  'compare.notYet': 'ابھی نہیں',
  'compare.viewDetails': 'تفصیل دیکھیں',

  'ptab.alerts': 'نئے میچ',
  'ptab.favorites': 'محفوظ گھر',
  'ptab.recent': 'دیکھے گئے',
  'ptab.hidden': 'چھپائے گئے',
  'panel.subtitle': 'آپ کے الرٹس اور محفوظ گھر',
  'alerts.dialogTitle': 'نئے گھروں کا الرٹ لگائیں',
  'alerts.dialogBody': 'ہم اس تلاش پر نظر رکھیں گے اور نئے میچ آتے ہی آپ کو دکھائیں گے۔',
  'alerts.watchingFor': 'کس چیز پر نظر ہے:',
  'alerts.allNew': 'تمام نئے گھر',
  'alerts.nameLabel': 'اس الرٹ کا نام',
  'alerts.newRentals': 'نئے گھر',
  'alerts.findUpdates': 'اپڈیٹس آپ کو {strong} میں ملیں گی۔ محفوظ کرنے کے بعد آپ ڈیوائس نوٹیفکیشنز بھی آن کر سکتے ہیں۔',
  'alerts.start': 'الرٹ شروع کریں',
  'alerts.save': 'الرٹ محفوظ کریں',
  'alerts.forThisSearch': '+ اس تلاش کا الرٹ',
  'alerts.createTitle': 'جو تلاش آپ دیکھ رہے ہیں اس کا الرٹ بنائیں',
  'alerts.chooseFirst': 'پہلے فلٹرز منتخب کریں، پھر الرٹ بنائیں',
  'alerts.noneYet': 'ابھی کوئی الرٹ نہیں',
  'alerts.neverMiss': 'کوئی اچھا گھر ہاتھ سے نہ جانے دیں',
  'alerts.howTo': 'اپنا شہر اور فلٹرز منتخب کریں، پھر اس تلاش کا الرٹ بنائیں۔ نئے میچ خود بخود یہاں جمع ہوتے رہیں گے۔',
  'alerts.yours': 'آپ کے الرٹس ({n})',
  'alerts.allRentals': 'تمام گھر',
  'alerts.newCount': '{n} نئے',
  'alerts.noMatches': 'ابھی کوئی میچ نہیں — ہم نظر رکھے ہوئے ہیں۔',
  'alerts.paused': 'رکا ہوا',
  'alerts.resume': 'دوبارہ شروع کریں',
  'alerts.pause': 'روکیں',
  'alerts.delete': 'حذف کریں',
  'alerts.confirmDelete': 'یہ الرٹ حذف کر دیں؟',
  'summary.beds': '{n} بیڈ',
  'summary.bedsRange': '{a} تا {b} بیڈ',
  'summary.in': '{place} میں',
  'summary.range': '{a} تا {b} ہزار روپے',
  'summary.under': '{v} ہزار روپے تک',
  'summary.over': '{v} ہزار روپے سے زیادہ',
  'summary.furnished': 'فرنشڈ',
  'summary.unfurnished': 'بغیر فرنیچر',
  'push.unsupported': 'اس براؤزر میں ڈیوائس نوٹیفکیشنز دستیاب نہیں۔ نئے میچ پھر بھی یہاں نظر آئیں گے۔',
  'push.blocked': 'براؤزر کی سیٹنگز میں نوٹیفکیشنز بند ہیں۔ نئے میچ پھر بھی یہاں نظر آئیں گے۔',
  'push.ask': 'نیا گھر ملنے پر فوراً اطلاع چاہیے؟',
  'push.notifyMe': 'مجھے اطلاع دیں',
  'push.reconnectMsg': 'اس ڈیوائس پر نوٹیفکیشنز کو ایک بار دوبارہ جوڑنا ہوگا۔',
  'push.reconnect': 'دوبارہ جوڑیں',
  'push.on': 'اس ڈیوائس پر نوٹیفکیشنز آن ہیں۔',
  'push.test': 'ٹیسٹ',
  'push.turnOff': 'بند کریں',
  'push.requesting': 'اجازت مانگی جا رہی ہے…',
  'toast.alertSaved': 'الرٹ محفوظ ہو گیا۔ ہم نئے میچ پر نظر رکھیں گے۔',
  'toast.alertError': 'الرٹ محفوظ نہیں ہو سکا۔',
  'toast.alertDeleted': 'الرٹ حذف ہو گیا۔',
  'toast.deleteFailed': 'حذف نہیں ہو سکا',
  'toast.updateFailed': 'اپڈیٹ نہیں ہو سکا',
  'toast.pushEnabled': 'نوٹیفکیشنز آن ہو گئے۔',
  'toast.pushDenied': 'نوٹیفکیشنز کی اجازت نہیں ملی۔',
  'toast.pushError': 'نوٹیفکیشنز آن نہیں ہو سکے۔',
  'toast.testSent': '{n} ڈیوائس پر ٹیسٹ نوٹیفکیشن بھیج دیا گیا۔',
  'toast.noSubs': 'کوئی نوٹیفکیشن سبسکرپشن نہیں ملی۔',
  'toast.testFailed': 'ٹیسٹ نوٹیفکیشن نہیں بھیجا جا سکا',
  'toast.pushOff': 'ڈیوائس نوٹیفکیشنز بند ہو گئے۔',
  'toast.pushOffError': 'نوٹیفکیشنز بند نہیں ہو سکے۔',
  'toast.favRemovedDot': 'پسندیدہ سے ہٹا دیا۔',
  'toast.unhidden': 'اشتہار دوبارہ نظر آئے گا۔',
  'fav.emptyTitle': 'ابھی کوئی گھر محفوظ نہیں',
  'fav.emptyBody': 'کسی بھی اشتہار پر دل کا نشان دبا کر اسے بعد کے لیے محفوظ کریں۔',
  'fav.count': 'محفوظ ({n})',
  'hidden.emptyTitle': 'کوئی اشتہار چھپایا نہیں گیا',
  'hidden.emptyBody': 'جو اشتہار پسند نہ ہوں انہیں چھپا کر اپنے نتائج صاف رکھیں۔',
  'hidden.count': 'چھپائے گئے ({n})',
  'recent.emptyTitle': 'ابھی کوئی اشتہار نہیں دیکھا',
  'recent.emptyBody': 'جو اشتہار آپ کھولیں گے وہ یہاں نظر آئیں گے تاکہ دوبارہ آسانی سے دیکھ سکیں۔',
  'recent.count': 'حال ہی میں دیکھے گئے ({n})',
  'saved.rental': 'کرائے کا گھر',
  'saved.savedAgo': '{rel} محفوظ کیا',
  'saved.hiddenAgo': '{rel} چھپایا',
  'saved.open': 'کھولیں',
  'saved.unhide': 'دوبارہ دکھائیں',
  'saved.remove': 'ہٹائیں',

  'welcome.question': '{city} میں آپ کو کیسا گھر چاہیے؟',
  'welcome.seeTips': 'مشورے دیکھیں',
  'welcome.dismissAria': 'تعارفی پٹی بند کریں',
  'welcome.browse': '{city} کے تازہ گھر دیکھیں',
  'welcome.title': 'اپنا کرائے کا گھر کیسے ڈھونڈیں',
  'welcome.body': 'اردو، رومن اردو یا انگریزی میں لکھ کر تلاش کریں، نیچے سے کوئی مثال چنیں، یا سیدھا تازہ ترین اشتہارات دیکھیں۔',
  'welcome.searchingIn': 'شہر',
  'welcome.orTry': 'یا یہ تلاش آزمائیں',
  'welcome.tour': 'مختصر تعارف دیکھیں',
  'welcome.skip': 'چھوڑیں',

  'tour.searchTitle': 'اپنے الفاظ میں تلاش کریں',
  'tour.searchBody': 'جو چاہیے لکھ دیں — جیسے "ڈی ایچ اے میں 2 بیڈ فلیٹ 50 ہزار تک" یا "DHA mein 2 bed flat 50k tak"۔ علاقہ، قسم، بیڈ روم اور بجٹ ہم خود نکال لیں گے۔',
  'tour.cityTitle': 'اپنا شہر چنیں',
  'tour.cityBody': 'لاہور، کراچی اور اسلام آباد میں سے چنیں۔ ہر شہر کے علاقے الگ لوڈ ہوتے ہیں اور نقشہ وہیں چلا جاتا ہے۔',
  'tour.filtersTitle': 'فلٹرز سے محدود کریں',
  'tour.filtersBody': 'علاقہ، قسم، بیڈ روم اور کرایہ چنیں — یا "میرے قریب" دبا کر اپنے آس پاس تلاش کریں۔',
  'tour.compareTitle': 'گھروں کا آمنے سامنے موازنہ',
  'tour.compareBody': 'کسی بھی اشتہار پر موازنے کا نشان دبائیں، پھر چار گھر تک ایک ہی جدول میں دیکھیں — فی مرلہ قیمت، فاصلہ، تازگی اور بہت کچھ۔',
  'tour.alertsTitle': 'گھر محفوظ کریں، الرٹ پائیں',
  'tour.alertsBody': '"میری فہرست" میں آپ کے پسندیدہ گھر، حال ہی میں دیکھے گئے اشتہارات اور نئے میچ کے الرٹس ہیں۔',
  'tour.mapTitle': 'نقشے پر دیکھیں',
  'tour.mapBody': 'محلے کے حساب سے دیکھیں — سبز نقطے اشتہار والے علاقے ہیں، سرخ نشان درست پتے ہیں۔',
  'tour.helpTitle': 'مدد ہمیشہ حاضر',
  'tour.helpBody': 'مشورے، تلاش کی مثالیں یا یہ تعارف دوبارہ دیکھنے کے لیے کسی بھی وقت مدد کا بٹن دبائیں۔',
  'tour.progress': '{{current}} از {{total}}',
  'tour.next': 'آگے',
  'tour.back': 'پیچھے',
  'tour.done': 'ٹھیک ہے',

  'voice.blocked': 'مائیکروفون کی اجازت بند ہے۔ بول کر تلاش کے لیے براؤزر کی سیٹنگز میں اجازت دیں۔',
  'voice.noMic': 'کوئی مائیکروفون نہیں ملا۔',
  'voice.cantStart': 'مائیکروفون شروع نہیں ہو سکا۔',
  'voice.stop': 'ریکارڈنگ روکیں',
  'voice.search': 'بول کر تلاش کریں',
  'voice.transcribing': 'آواز کو لکھا جا رہا ہے...',
  'voice.transcribeError': 'آواز سمجھ نہیں آئی۔ دوبارہ کوشش کریں۔',
  'voice.didntCatch': 'سمجھ نہیں آیا۔ مائیک دبا کر دوبارہ بولیں۔',
  'voice.recordFailed': 'ریکارڈنگ نہیں ہو سکی۔ مائیک دبا کر دوبارہ کوشش کریں۔',
  'voice.recordStartFailed': 'ریکارڈنگ شروع نہیں ہو سکی۔ مائیک دبا کر دوبارہ کوشش کریں۔',
  'voice.listening': 'سن رہے ہیں...',
  'voice.tapStop': ' · روکنے کے لیے دبائیں',

  'sw.updated': 'ایپ اپڈیٹ ہو گئی۔ نیا ورژن دیکھنے کے لیے ریفریش کریں۔',
  'sw.refresh': 'ریفریش',
  'sw.queuedSent': 'محفوظ شدہ رائے بھیج دی گئی۔',

  'time.justNow': 'ابھی ابھی',
  'time.minutes': '{n} منٹ پہلے',
  'time.hours_one': '{n} گھنٹہ پہلے',
  'time.hours': '{n} گھنٹے پہلے',
  'time.days': '{n} دن پہلے',
  'time.weeks_one': '{n} ہفتہ پہلے',
  'time.weeks': '{n} ہفتے پہلے',
  'time.months_one': '{n} مہینہ پہلے',
  'time.months': '{n} مہینے پہلے',
  'time.years': '{n} سال پہلے',
};

const DICTS = { en, ur };

function readInitialLang() {
  try {
    const fromUrl = new URLSearchParams(location.search).get('lang');
    if (LANGS.includes(fromUrl)) {
      try { localStorage.setItem(LANG_KEY, fromUrl); } catch {}
      return fromUrl;
    }
  } catch {}
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (LANGS.includes(stored)) return stored;
  } catch {}
  return 'en';
}

let _lang = readInitialLang();
const _listeners = new Set();

export function getLang() { return _lang; }
export function isRtl() { return _lang === 'ur'; }

export function t(key, vars) {
  const dict = DICTS[_lang] || en;
  let s;
  if (vars && Number(vars.n) === 1) s = dict[key + '_one'];
  if (s == null) s = dict[key] ?? en[key] ?? key;
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, name) => (vars[name] != null ? String(vars[name]) : m));
}

/** Subscribe to language changes. Returns an unsubscribe function. */
export function onLangChange(fn) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

export function setLang(lang) {
  if (!LANGS.includes(lang) || lang === _lang) return;
  _lang = lang;
  try { localStorage.setItem(LANG_KEY, lang); } catch {}
  // Keep a shared ?lang= link from flipping the choice back on reload.
  try {
    const url = new URL(location.href);
    if (url.searchParams.has('lang')) {
      if (lang === 'ur') url.searchParams.set('lang', 'ur');
      else url.searchParams.delete('lang');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
  } catch {}
  applyDocumentLang();
  applyTranslations();
  for (const fn of _listeners) {
    try { fn(lang); } catch (err) { console.warn('language listener error', err); }
  }
}

export function applyDocumentLang() {
  const root = document.documentElement;
  root.lang = _lang;
  root.dir = _lang === 'ur' ? 'rtl' : 'ltr';
  document.title = t('app.title');
  document.querySelector('meta[name="description"]')?.setAttribute('content', t('app.description'));
  document.querySelectorAll('[data-lang-option]').forEach(btn => {
    const on = btn.dataset.langOption === _lang;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-pressed', String(on));
  });
}

const ATTRS = [
  ['i18nPlaceholder', 'placeholder'],
  ['i18nTitle', 'title'],
  ['i18nAriaLabel', 'aria-label'],
];

/** Fill every `data-i18n*` element under `root` with the active language. */
export function applyTranslations(root = document) {
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  for (const [dataKey, attr] of ATTRS) {
    const sel = '[data-' + dataKey.replace(/[A-Z]/g, c => '-' + c.toLowerCase()) + ']';
    root.querySelectorAll(sel).forEach(el => el.setAttribute(attr, t(el.dataset[dataKey])));
  }
}

/** Wire the header English / اردو switch and paint the static page once. */
export function initI18n() {
  applyDocumentLang();
  applyTranslations();
  document.querySelectorAll('[data-lang-option]').forEach(btn => {
    btn.addEventListener('click', () => setLang(btn.dataset.langOption));
  });
}

// ── Formatting helpers ───────────────────────────────────────────────────────

/** Western digits with thousands separators, whatever the browser locale. */
export function fmtNum(n) {
  return Number(n).toLocaleString('en-US');
}

function trimDecimals(v, places = 2) {
  return String(Number(v.toFixed(places)));
}

/** Short budget label for chips: "50K" in English, "50 ہزار" / "1.5 لاکھ" in Urdu. */
export function fmtShortPrice(v) {
  const n = Number(v);
  if (_lang !== 'ur') return (n / 1e3 | 0) + 'K';
  if (n >= 1e7) return trimDecimals(n / 1e7) + ' کروڑ';
  if (n >= 1e5) return trimDecimals(n / 1e5) + ' لاکھ';
  return (n / 1e3 | 0) + ' ہزار';
}

const PRICE_UNITS_UR = [
  [/\bArab\b/gi, 'ارب'], [/\bCrore\b/gi, 'کروڑ'], [/\bLakh\b/gi, 'لاکھ'],
  [/\bThousand\b/gi, 'ہزار'], [/\bPKR\b/gi, 'روپے'],
];

/** Urdu wording for a price, from Zameen's text ("2.4 Lakh") or the number. */
export function fmtPriceUr(p, text) {
  if (text) {
    // "PKR 50 Thousand" → "50 ہزار": the card already says it is rent per month.
    const bare = String(text).replace(/^\s*(PKR|Rs\.?)\s*/i, '');
    return PRICE_UNITS_UR.reduce((s, [re, word]) => s.replace(re, word), bare);
  }
  if (!p) return t('price.onRequest');
  if (p >= 1e7) return trimDecimals(p / 1e7) + ' کروڑ';
  if (p >= 1e5) return trimDecimals(p / 1e5) + ' لاکھ';
  if (p >= 1e3) return trimDecimals(p / 1e3, 1) + ' ہزار';
  return fmtNum(p) + ' روپے';
}

const SIZE_UNITS_UR = [
  [/Sq\.?\s*Yd\.?|Square\s*Yards?/gi, 'گز'], [/Sq\.?\s*Ft\.?|Square\s*Feet/gi, 'مربع فٹ'],
  [/Sq\.?\s*M\.?/gi, 'مربع میٹر'], [/\bMarla\b/gi, 'مرلہ'], [/\bKanal\b/gi, 'کنال'],
];

/** "500 Sq. Yd." → "500 گز" in Urdu; unchanged in English. */
export function localizeAreaSize(size) {
  if (!size || _lang !== 'ur') return size;
  return SIZE_UNITS_UR.reduce((s, [re, word]) => s.replace(re, word), String(size));
}

const PROPERTY_TYPES_UR = {
  'house': 'گھر', 'apartment / flat': 'فلیٹ', 'apartment': 'فلیٹ', 'flat': 'فلیٹ',
  'upper portion': 'اپر پورشن', 'lower portion': 'لوئر پورشن', 'portion': 'پورشن',
  'room': 'کمرہ', 'penthouse': 'پینٹ ہاؤس', 'farm house': 'فارم ہاؤس',
};

/** Translate a property-type label that came from the backend ("Apartment / Flat"). */
export function propertyTypeLabel(label) {
  if (!label || _lang !== 'ur') return label;
  return PROPERTY_TYPES_UR[String(label).trim().toLowerCase()] || label;
}

export function cityLabel(key) {
  return key ? t('city.' + key) : '';
}

/** Urdu area name from /api/areas `name_ur` when one exists; otherwise the English name. */
export function areaLabel(name) {
  if (!name || _lang !== 'ur') return name;
  const hit = refs.allAreas?.find?.(a => a.name === name);
  return hit?.name_ur || name;
}

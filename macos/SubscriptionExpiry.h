#ifndef CODEX_QUOTA_SUBSCRIPTION_EXPIRY_H
#define CODEX_QUOTA_SUBSCRIPTION_EXPIRY_H

#import <Foundation/Foundation.h>

static inline NSCalendar *CQMSubscriptionCalendar(void) {
    NSCalendar *calendar = [[NSCalendar alloc] initWithCalendarIdentifier:NSCalendarIdentifierGregorian];
    calendar.timeZone = NSTimeZone.localTimeZone;
    return calendar;
}

// Resolve a configured day-of-month to the nearest matching local calendar day.
// A smaller day number belongs to the next month; an equal or larger one belongs
// to the current month. Months that do not contain the requested day are skipped.
static inline NSDate *CQMSubscriptionExpirationForDay(NSInteger day, NSDate *now) {
    if (day < 1 || day > 31 || !now) return nil;

    NSCalendar *calendar = CQMSubscriptionCalendar();
    NSDate *todayStart = [calendar startOfDayForDate:now];
    NSDateComponents *today = [calendar components:(NSCalendarUnitYear |
                                                     NSCalendarUnitMonth |
                                                     NSCalendarUnitDay)
                                           fromDate:todayStart];
    NSDateComponents *monthParts = [[NSDateComponents alloc] init];
    monthParts.year = today.year;
    monthParts.month = today.month;
    monthParts.day = 1;
    NSDate *monthStart = [calendar dateFromComponents:monthParts];
    if (day < today.day) {
        monthStart = [calendar dateByAddingUnit:NSCalendarUnitMonth
                                          value:1
                                         toDate:monthStart
                                        options:0];
    }

    for (NSInteger offset = 0; offset < 24; offset++) {
        NSDate *candidateMonth = [calendar dateByAddingUnit:NSCalendarUnitMonth
                                                       value:offset
                                                      toDate:monthStart
                                                     options:0];
        NSDateComponents *month = [calendar components:(NSCalendarUnitYear | NSCalendarUnitMonth)
                                              fromDate:candidateMonth];
        NSDateComponents *candidateParts = [[NSDateComponents alloc] init];
        candidateParts.year = month.year;
        candidateParts.month = month.month;
        candidateParts.day = day;
        NSDate *candidateStart = [calendar dateFromComponents:candidateParts];
        if (!candidateStart) continue;

        NSDateComponents *verified = [calendar components:(NSCalendarUnitYear |
                                                           NSCalendarUnitMonth |
                                                           NSCalendarUnitDay)
                                                 fromDate:candidateStart];
        if (verified.year != month.year || verified.month != month.month || verified.day != day) {
            continue;
        }
        if ([candidateStart compare:todayStart] == NSOrderedAscending) continue;

        NSDate *nextDay = [calendar dateByAddingUnit:NSCalendarUnitDay
                                               value:1
                                              toDate:candidateStart
                                             options:0];
        return [nextDay dateByAddingTimeInterval:-1.0];
    }
    return nil;
}

// Count local calendar days inclusively. The configured date remains valid for
// its entire local day, so an expiry today displays as one remaining day.
static inline NSInteger CQMSubscriptionRemainingDays(NSDate *expiration, NSDate *now) {
    if (!expiration || !now) return 0;
    NSCalendar *calendar = CQMSubscriptionCalendar();
    NSDate *todayStart = [calendar startOfDayForDate:now];
    NSDate *expirationStart = [calendar startOfDayForDate:expiration];
    NSInteger difference = [[calendar components:NSCalendarUnitDay
                                         fromDate:todayStart
                                           toDate:expirationStart
                                          options:0] day];
    return difference < 0 ? 0 : difference + 1;
}

#endif

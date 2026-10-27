#ifndef CODEX_QUOTA_JWT_SUBSCRIPTION_H
#define CODEX_QUOTA_JWT_SUBSCRIPTION_H

#import <Foundation/Foundation.h>
#import <math.h>

static inline NSData *CQMDecodeJWTPart(NSString *part) {
    if (![part isKindOfClass:NSString.class] || part.length == 0) return nil;
    NSMutableString *base64 = [part mutableCopy];
    [base64 replaceOccurrencesOfString:@"-" withString:@"+" options:0 range:NSMakeRange(0, base64.length)];
    [base64 replaceOccurrencesOfString:@"_" withString:@"/" options:0 range:NSMakeRange(0, base64.length)];
    while (base64.length % 4 != 0) [base64 appendString:@"="];
    return [[NSData alloc] initWithBase64EncodedString:base64 options:0];
}

// Decode only the JWT payload and read the dedicated subscription claim. The
// ordinary JWT `exp` claim is intentionally ignored because it is the login
// token expiry, not the ChatGPT subscription expiry.
static inline NSDate *CQMSubscriptionExpirationFromIDToken(NSString *idToken) {
    if (![idToken isKindOfClass:NSString.class]) return nil;
    NSArray<NSString *> *parts = [idToken componentsSeparatedByString:@"."];
    if (parts.count != 3) return nil;

    NSData *payloadData = CQMDecodeJWTPart(parts[1]);
    if (!payloadData || payloadData.length > 1024 * 1024) return nil;
    id payloadObject = [NSJSONSerialization JSONObjectWithData:payloadData options:0 error:nil];
    if (![payloadObject isKindOfClass:NSDictionary.class]) return nil;
    NSDictionary *payload = payloadObject;
    NSDictionary *auth = [payload[@"https://api.openai.com/auth"] isKindOfClass:NSDictionary.class]
        ? payload[@"https://api.openai.com/auth"]
        : nil;
    id rawExpiration = auth[@"chatgpt_subscription_active_until"];
    if (![rawExpiration isKindOfClass:NSString.class]) return nil;

    NSString *text = [(NSString *)rawExpiration stringByTrimmingCharactersInSet:
        NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (text.length == 0) return nil;
    NSISO8601DateFormatter *formatter = [[NSISO8601DateFormatter alloc] init];
    NSDate *date = [formatter dateFromString:text];
    if (!date) {
        formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime |
                                  NSISO8601DateFormatWithFractionalSeconds;
        date = [formatter dateFromString:text];
    }
    return date;
}

static inline NSDate *CQMSubscriptionExpirationFromAuthFile(NSString *path) {
    if (![path isKindOfClass:NSString.class] || path.length == 0) return nil;
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    unsigned long long fileSize = [attributes[NSFileSize] unsignedLongLongValue];
    if (fileSize == 0 || fileSize > 4 * 1024 * 1024) return nil;

    NSData *data = [NSData dataWithContentsOfFile:path options:0 error:nil];
    if (!data) return nil;
    id rootObject = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![rootObject isKindOfClass:NSDictionary.class]) return nil;
    NSDictionary *tokens = [rootObject[@"tokens"] isKindOfClass:NSDictionary.class]
        ? rootObject[@"tokens"]
        : nil;
    NSString *idToken = [tokens[@"id_token"] isKindOfClass:NSString.class]
        ? tokens[@"id_token"]
        : nil;
    return CQMSubscriptionExpirationFromIDToken(idToken);
}

static inline BOOL CQMSubscriptionPlanRenewsMonthly(NSString *plan) {
    if (![plan isKindOfClass:NSString.class]) return NO;
    NSString *normalized = [[plan stringByTrimmingCharactersInSet:
        NSCharacterSet.whitespaceAndNewlineCharacterSet] lowercaseString];
    return [normalized isEqualToString:@"plus"] || [normalized isEqualToString:@"pro"];
}

// A stale JWT can retain the previous billing timestamp after an automatic
// monthly renewal. Only infer the next billing date when the live official
// quota response still identifies the account as Plus or Pro.
static inline NSDate *CQMEffectiveSubscriptionExpiration(NSDate *expiration,
                                                         NSDate *now,
                                                         NSString *plan,
                                                         BOOL *inferredRenewal) {
    if (inferredRenewal) *inferredRenewal = NO;
    if (!expiration || !now || [expiration compare:now] == NSOrderedDescending) return expiration;
    if (!CQMSubscriptionPlanRenewsMonthly(plan)) return expiration;

    NSCalendar *calendar = [[NSCalendar alloc] initWithCalendarIdentifier:NSCalendarIdentifierGregorian];
    calendar.timeZone = NSTimeZone.localTimeZone;
    NSDate *adjusted = expiration;
    for (NSInteger month = 0; month < 120 && [adjusted compare:now] != NSOrderedDescending; month++) {
        NSDate *next = [calendar dateByAddingUnit:NSCalendarUnitMonth
                                            value:1
                                           toDate:adjusted
                                          options:0];
        if (!next || [next compare:adjusted] != NSOrderedDescending) break;
        adjusted = next;
    }
    if ([adjusted compare:now] == NSOrderedDescending && ![adjusted isEqualToDate:expiration]) {
        if (inferredRenewal) *inferredRenewal = YES;
        return adjusted;
    }
    return expiration;
}

// Display partial remaining days as one day without double-counting both the
// current date and the expiry date. For example, Oct 27 to Nov 27 is 31 days.
static inline NSInteger CQMSubscriptionRemainingDays(NSDate *expiration, NSDate *now) {
    if (!expiration || !now) return 0;
    NSTimeInterval remaining = [expiration timeIntervalSinceDate:now];
    if (remaining <= 0) return 0;
    return MAX(1, (NSInteger)ceil(remaining / (24.0 * 60.0 * 60.0)));
}

#endif

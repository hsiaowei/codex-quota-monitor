#import <Cocoa/Cocoa.h>

static NSColor *QuotaGreen(void) {
    return [NSColor colorWithCalibratedRed:0.063 green:0.639 blue:0.498 alpha:1.0];
}

static NSColor *QuotaRed(void) {
    return [NSColor colorWithCalibratedRed:0.898 green:0.282 blue:0.302 alpha:1.0];
}

static NSColor *QuotaYellow(void) {
    return [NSColor colorWithCalibratedRed:0.78 green:0.50 blue:0.04 alpha:1.0];
}

static NSColor *QuotaText(void) {
    return [NSColor colorWithCalibratedRed:0.09 green:0.13 blue:0.20 alpha:1.0];
}

static NSColor *QuotaMuted(void) {
    return [NSColor colorWithCalibratedRed:0.40 green:0.44 blue:0.52 alpha:1.0];
}

static NSError *QuotaError(NSString *message) {
    return [NSError errorWithDomain:@"CodexQuotaMenu"
                               code:1
                           userInfo:@{NSLocalizedDescriptionKey: message}];
}

static NSString *QuotaCodexHome(void) {
    NSString *codexHome = NSProcessInfo.processInfo.environment[@"CODEX_HOME"];
    return codexHome.length > 0 ? [codexHome stringByExpandingTildeInPath]
                                : [@"~/.codex" stringByExpandingTildeInPath];
}

static NSDateFormatter *QuotaDayFormatter(void) {
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    formatter.calendar = [[NSCalendar alloc] initWithCalendarIdentifier:NSCalendarIdentifierGregorian];
    formatter.dateFormat = @"yyyy-MM-dd";
    return formatter;
}

static NSDictionary *QuotaWeeklyWindowFromLimits(NSDictionary *limits) {
    if (![limits isKindOfClass:NSDictionary.class]) return nil;
    NSMutableArray<NSDictionary *> *buckets = [NSMutableArray array];
    NSDictionary *single = limits[@"rateLimits"];
    if ([single isKindOfClass:NSDictionary.class]) [buckets addObject:single];
    NSDictionary *byID = limits[@"rateLimitsByLimitId"];
    if ([byID isKindOfClass:NSDictionary.class]) {
        for (id value in byID.allValues) {
            if ([value isKindOfClass:NSDictionary.class]) [buckets addObject:value];
        }
    }
    if ([limits[@"primary"] isKindOfClass:NSDictionary.class] ||
        [limits[@"secondary"] isKindOfClass:NSDictionary.class]) {
        [buckets addObject:limits];
    }
    for (NSDictionary *bucket in buckets) {
        for (NSString *kind in @[@"primary", @"secondary"]) {
            NSDictionary *window = bucket[kind];
            NSNumber *used = [window isKindOfClass:NSDictionary.class] ? window[@"usedPercent"] : nil;
            NSNumber *duration = [window isKindOfClass:NSDictionary.class] ? window[@"windowDurationMins"] : nil;
            if ([used isKindOfClass:NSNumber.class] && [duration isKindOfClass:NSNumber.class] &&
                duration.integerValue == 10080) {
                NSMutableDictionary *result = [window mutableCopy];
                result[@"kind"] = kind;
                if ([bucket[@"limitId"] isKindOfClass:NSString.class]) result[@"limitId"] = bucket[@"limitId"];
                return result;
            }
        }
    }
    return nil;
}

@interface QuotaDailyUsageTracker : NSObject
- (NSDictionary *)recordWeeklyUsedPercent:(double)used atDate:(NSDate *)date;
@end

@implementation QuotaDailyUsageTracker

- (NSString *)cachePath {
    return [[QuotaCodexHome() stringByAppendingPathComponent:@"codex-quota-monitor"]
            stringByAppendingPathComponent:@"daily-weekly-quota-cache.json"];
}

- (NSDictionary *)loadState {
    NSData *data = [NSData dataWithContentsOfFile:[self cachePath]];
    NSDictionary *payload = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    return [payload isKindOfClass:NSDictionary.class] && [payload[@"version"] integerValue] == 1 ? payload : @{};
}

- (NSDictionary *)recordWeeklyUsedPercent:(double)used atDate:(NSDate *)date {
    @synchronized (self) {
        NSDate *observedDate = date ?: NSDate.date;
        NSTimeInterval observedAt = observedDate.timeIntervalSince1970;
        NSString *day = [QuotaDayFormatter() stringFromDate:observedDate];
        NSDictionary *previous = [self loadState];
        BOOL sameDay = [previous[@"day"] isEqual:day];
        NSNumber *rawAccumulated = sameDay ? previous[@"accumulatedIncreasePercent"] : nil;
        NSNumber *rawLast = sameDay ? previous[@"lastUsedPercent"] : nil;
        NSNumber *rawStarted = sameDay ? previous[@"trackingStartedAt"] : nil;
        double accumulated = [rawAccumulated isKindOfClass:NSNumber.class] ? MAX(0, rawAccumulated.doubleValue) : 0;
        double current = MAX(0, MIN(100, used));
        if ([rawLast isKindOfClass:NSNumber.class] && current > rawLast.doubleValue) {
            accumulated += current - rawLast.doubleValue;
        }
        NSNumber *startedAt = [rawStarted isKindOfClass:NSNumber.class] ? rawStarted : @((long long)observedAt);
        NSDictionary *payload = @{
            @"version": @1,
            @"day": day,
            @"trackingStartedAt": startedAt,
            @"lastObservedAt": @((long long)observedAt),
            @"lastUsedPercent": @(current),
            @"accumulatedIncreasePercent": @(accumulated)
        };
        NSString *path = [self cachePath];
        [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                                withIntermediateDirectories:YES
                                                 attributes:nil
                                                      error:nil];
        NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
        if (data) [data writeToFile:path options:NSDataWritingAtomic error:nil];
        return @{
            @"usedPercent": @(accumulated),
            @"trackingStartedAt": startedAt,
            @"lastObservedAt": @((long long)observedAt)
        };
    }
}
@end

@interface CodexQuotaClient : NSObject
- (instancetype)initWithTracker:(QuotaDailyUsageTracker *)tracker;
- (NSDictionary *)fetch:(NSError **)error;
@end

@implementation CodexQuotaClient {
    QuotaDailyUsageTracker *_tracker;
}

- (instancetype)initWithTracker:(QuotaDailyUsageTracker *)tracker {
    self = [super init];
    if (self) _tracker = tracker;
    return self;
}

- (NSString *)codexPath {
    NSFileManager *manager = NSFileManager.defaultManager;
    NSArray<NSString *> *fixed = @[@"/usr/local/bin/codex", @"/opt/homebrew/bin/codex"];
    for (NSString *path in fixed) {
        if ([manager isExecutableFileAtPath:path]) return path;
    }
    NSString *pathValue = NSProcessInfo.processInfo.environment[@"PATH"];
    for (NSString *directory in [pathValue componentsSeparatedByString:@":"]) {
        NSString *candidate = [directory stringByAppendingPathComponent:@"codex"];
        if ([manager isExecutableFileAtPath:candidate]) return candidate;
    }
    return nil;
}

- (NSDictionary *)resultFromMessage:(NSDictionary *)message name:(NSString *)name error:(NSError **)error {
    NSDictionary *serverError = message[@"error"];
    if ([serverError isKindOfClass:NSDictionary.class]) {
        if (error) *error = QuotaError(serverError[@"message"] ?: name);
        return nil;
    }
    NSDictionary *result = message[@"result"];
    if (![result isKindOfClass:NSDictionary.class]) {
        if (error) *error = QuotaError([NSString stringWithFormat:@"%@数据无效", name]);
        return nil;
    }
    return result;
}

- (NSString *)maskedEmail:(NSString *)email {
    if (![email isKindOfClass:NSString.class]) return @"ChatGPT 账号";
    NSRange at = [email rangeOfString:@"@"];
    if (at.location == NSNotFound) return @"ChatGPT 账号";
    NSString *local = [email substringToIndex:at.location];
    NSString *domain = [email substringFromIndex:at.location + 1];
    NSUInteger prefixLength = MIN((NSUInteger)2, local.length);
    NSString *prefix = [local substringToIndex:prefixLength];
    NSUInteger starCount = MIN((NSUInteger)5, MAX((NSUInteger)1, local.length > 2 ? local.length - 2 : 1));
    return [NSString stringWithFormat:@"%@%@@%@", prefix,
            [@"*****" substringToIndex:starCount], domain];
}

- (NSString *)windowLabel:(NSInteger)minutes {
    if (minutes == 10080) return @"周额度";
    if (minutes > 0 && minutes % 1440 == 0) return [NSString stringWithFormat:@"%ld 天窗口", (long)(minutes / 1440)];
    if (minutes > 0 && minutes % 60 == 0) return [NSString stringWithFormat:@"%ld 小时窗口", (long)(minutes / 60)];
    return [NSString stringWithFormat:@"%ld 分钟窗口", (long)minutes];
}

- (NSDateFormatter *)dayFormatter {
    return QuotaDayFormatter();
}

- (NSString *)officialUsageCachePath {
    return [[QuotaCodexHome() stringByAppendingPathComponent:@"codex-quota-monitor"]
            stringByAppendingPathComponent:@"official-usage-cache.json"];
}

- (NSMutableDictionary<NSString *, NSNumber *> *)officialDailyUsage:(NSDictionary *)usageResult {
    NSMutableDictionary<NSString *, NSNumber *> *official = [NSMutableDictionary dictionary];
    NSArray *dailyBuckets = usageResult[@"dailyUsageBuckets"];
    if (![dailyBuckets isKindOfClass:NSArray.class]) return official;
    for (NSDictionary *bucket in dailyBuckets) {
        NSString *day = [bucket isKindOfClass:NSDictionary.class] ? bucket[@"startDate"] : nil;
        NSNumber *tokens = [bucket isKindOfClass:NSDictionary.class] ? bucket[@"tokens"] : nil;
        if ([day isKindOfClass:NSString.class] && [tokens isKindOfClass:NSNumber.class]) {
            official[day] = @(MAX(0, tokens.longLongValue));
        }
    }
    return official;
}

- (void)saveOfficialDailyUsage:(NSDictionary<NSString *, NSNumber *> *)official fetchedAt:(NSTimeInterval)fetchedAt {
    if (official.count == 0) return;
    NSString *path = [self officialUsageCachePath];
    NSString *directory = path.stringByDeletingLastPathComponent;
    [NSFileManager.defaultManager createDirectoryAtPath:directory
                            withIntermediateDirectories:YES
                                             attributes:nil
                                                  error:nil];
    NSDictionary *payload = @{
        @"version": @1,
        @"fetchedAt": @((long long)fetchedAt),
        @"dailyUsageTokens": official
    };
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    if (data) [data writeToFile:path options:NSDataWritingAtomic error:nil];
}

- (NSDictionary *)loadOfficialDailyUsageCache {
    NSData *data = [NSData dataWithContentsOfFile:[self officialUsageCachePath]];
    NSDictionary *payload = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    NSDictionary *rawDaily = [payload isKindOfClass:NSDictionary.class] ? payload[@"dailyUsageTokens"] : nil;
    NSNumber *fetchedAt = [payload isKindOfClass:NSDictionary.class] ? payload[@"fetchedAt"] : nil;
    if (![rawDaily isKindOfClass:NSDictionary.class] || ![fetchedAt isKindOfClass:NSNumber.class]) return nil;
    NSMutableDictionary<NSString *, NSNumber *> *daily = [NSMutableDictionary dictionary];
    for (id rawDay in rawDaily) {
        id rawTokens = rawDaily[rawDay];
        if ([rawDay isKindOfClass:NSString.class] && [rawTokens isKindOfClass:NSNumber.class]) {
            daily[rawDay] = @(MAX(0, [rawTokens longLongValue]));
        }
    }
    return daily.count > 0 ? @{@"daily": daily, @"fetchedAt": fetchedAt} : nil;
}

- (NSDate *)eventDate:(NSString *)value {
    if (![value isKindOfClass:NSString.class]) return nil;
    NSISO8601DateFormatter *fractional = [[NSISO8601DateFormatter alloc] init];
    fractional.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    NSDate *date = [fractional dateFromString:value];
    if (date) return date;
    NSISO8601DateFormatter *plain = [[NSISO8601DateFormatter alloc] init];
    plain.formatOptions = NSISO8601DateFormatWithInternetDateTime;
    return [plain dateFromString:value];
}

- (NSNumber *)localTokensForDate:(NSDate *)targetDate {
    NSURL *sessionsURL = [NSURL fileURLWithPath:[QuotaCodexHome() stringByAppendingPathComponent:@"sessions"] isDirectory:YES];
    NSFileManager *manager = NSFileManager.defaultManager;
    BOOL isDirectory = NO;
    if (![manager fileExistsAtPath:sessionsURL.path isDirectory:&isDirectory] || !isDirectory) return nil;

    NSCalendar *calendar = NSCalendar.currentCalendar;
    NSDate *dayStart = [calendar startOfDayForDate:targetDate];
    NSArray *keys = @[NSURLContentModificationDateKey, NSURLIsRegularFileKey];
    NSDirectoryEnumerator<NSURL *> *files = [manager enumeratorAtURL:sessionsURL
                                         includingPropertiesForKeys:keys
                                                            options:NSDirectoryEnumerationSkipsHiddenFiles
                                                       errorHandler:^BOOL(NSURL *url, NSError *scanError) { return YES; }];
    __block long long total = 0;
    for (NSURL *fileURL in files) {
        if (![[fileURL.pathExtension lowercaseString] isEqualToString:@"jsonl"]) continue;
        NSNumber *regular = nil;
        NSDate *modified = nil;
        [fileURL getResourceValue:&regular forKey:NSURLIsRegularFileKey error:nil];
        [fileURL getResourceValue:&modified forKey:NSURLContentModificationDateKey error:nil];
        if (!regular.boolValue || (modified && [modified compare:dayStart] == NSOrderedAscending)) continue;

        NSString *contents = [NSString stringWithContentsOfURL:fileURL encoding:NSUTF8StringEncoding error:nil];
        if (!contents) continue;
        [contents enumerateLinesUsingBlock:^(NSString *line, BOOL *stop) {
            NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
            NSDictionary *record = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
            if (![record isKindOfClass:NSDictionary.class] || ![record[@"type"] isEqual:@"event_msg"]) return;
            NSDate *eventDate = [self eventDate:record[@"timestamp"]];
            if (!eventDate || ![calendar isDate:eventDate inSameDayAsDate:targetDate]) return;
            NSDictionary *payload = record[@"payload"];
            if (![payload isKindOfClass:NSDictionary.class] || ![payload[@"type"] isEqual:@"token_count"]) return;
            NSDictionary *info = payload[@"info"];
            NSDictionary *last = [info isKindOfClass:NSDictionary.class] ? info[@"last_token_usage"] : nil;
            NSNumber *tokens = [last isKindOfClass:NSDictionary.class] ? last[@"total_tokens"] : nil;
            if ([tokens isKindOfClass:NSNumber.class]) total += MAX(0, tokens.longLongValue);
        }];
    }
    return @(total);
}

- (NSDictionary *)usageStats:(NSDictionary *)usageResult {
    NSDate *now = NSDate.date;
    NSCalendar *calendar = NSCalendar.currentCalendar;
    calendar.firstWeekday = 2;
    NSDate *today = [calendar startOfDayForDate:now];
    NSDateFormatter *formatter = [self dayFormatter];

    NSMutableDictionary<NSString *, NSNumber *> *official = [self officialDailyUsage:usageResult];
    BOOL officialIsCached = NO;
    NSNumber *officialCacheFetchedAt = nil;
    if (official.count > 0) {
        [self saveOfficialDailyUsage:official fetchedAt:now.timeIntervalSince1970];
    } else {
        NSDictionary *cache = [self loadOfficialDailyUsageCache];
        NSDictionary *cachedDaily = cache[@"daily"];
        if ([cachedDaily isKindOfClass:NSDictionary.class] && cachedDaily.count > 0) {
            official = [cachedDaily mutableCopy];
            officialIsCached = YES;
            officialCacheFetchedAt = cache[@"fetchedAt"];
        }
    }

    NSDate *comparison = [calendar dateByAddingUnit:NSCalendarUnitDay value:-1 toDate:today options:0];
    BOOL weekendFallback = NO;
    while (YES) {
        NSInteger comparisonWeekday = [calendar component:NSCalendarUnitWeekday fromDate:comparison];
        if (comparisonWeekday != 1 && comparisonWeekday != 7) break;
        weekendFallback = YES;
        comparison = [calendar dateByAddingUnit:NSCalendarUnitDay value:-1 toDate:comparison options:0];
    }

    NSInteger weekday = [calendar component:NSCalendarUnitWeekday fromDate:today];
    NSInteger daysSinceMonday = (weekday + 5) % 7;
    NSDate *weekStart = [calendar dateByAddingUnit:NSCalendarUnitDay value:-daysSinceMonday toDate:today options:0];
    NSDateComponents *monthParts = [calendar components:(NSCalendarUnitYear | NSCalendarUnitMonth) fromDate:today];
    monthParts.day = 1;
    NSDate *monthStart = [calendar dateFromComponents:monthParts];

    long long officialWeek = 0;
    long long officialMonth = 0;
    NSString *latestOfficial = nil;
    for (NSString *dayString in official) {
        NSDate *bucketDate = [formatter dateFromString:dayString];
        if (!bucketDate || [bucketDate compare:today] != NSOrderedAscending) continue;
        long long tokens = MAX(0, official[dayString].longLongValue);
        if ([bucketDate compare:weekStart] != NSOrderedAscending) officialWeek += tokens;
        if ([bucketDate compare:monthStart] != NSOrderedAscending) officialMonth += tokens;
        if (!latestOfficial || [dayString compare:latestOfficial] == NSOrderedDescending) latestOfficial = dayString;
    }

    NSNumber *todayTokens = [self localTokensForDate:today];
    long long localToday = [todayTokens isKindOfClass:NSNumber.class] ? MAX(0, todayTokens.longLongValue) : 0;
    NSMutableDictionary *stats = [@{
        @"todayDate": [formatter stringFromDate:today],
        @"comparisonDate": [formatter stringFromDate:comparison],
        @"comparisonLabel": weekendFallback ? @"上周五" : @"昨日",
        @"officialIsCached": @(officialIsCached)
    } mutableCopy];
    if (todayTokens) stats[@"todayTokens"] = todayTokens;
    if (official.count > 0) {
        stats[@"weekTokens"] = @(officialWeek + localToday);
        stats[@"monthTokens"] = @(officialMonth + localToday);
        stats[@"weekOfficialTokens"] = @(officialWeek);
        stats[@"monthOfficialTokens"] = @(officialMonth);
    }
    NSNumber *comparisonTokens = official[stats[@"comparisonDate"]];
    if (comparisonTokens) stats[@"comparisonTokens"] = comparisonTokens;
    if (latestOfficial) stats[@"officialLatestDate"] = latestOfficial;
    if (officialIsCached && officialCacheFetchedAt) stats[@"officialCacheFetchedAt"] = officialCacheFetchedAt;
    return stats;
}

- (NSDictionary *)fetch:(NSError **)error {
    NSString *codex = [self codexPath];
    if (!codex) {
        if (error) *error = QuotaError(@"找不到 Codex CLI");
        return nil;
    }

    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:codex];
    task.arguments = @[@"app-server"];
    NSPipe *input = [NSPipe pipe];
    NSPipe *output = [NSPipe pipe];
    task.standardInput = input;
    task.standardOutput = output;
    task.standardError = [NSFileHandle fileHandleWithNullDevice];

    NSError *launchError = nil;
    if (![task launchAndReturnError:&launchError]) {
        if (error) *error = QuotaError([NSString stringWithFormat:@"无法启动额度接口：%@", launchError.localizedDescription]);
        return nil;
    }

    NSArray *requests = @[
        @{@"method": @"initialize", @"id": @0,
          @"params": @{@"clientInfo": @{@"name": @"codex_quota_menu",
                                           @"title": @"Codex Quota Menu",
                                           @"version": @"0.6.1"}}},
        @{@"method": @"initialized", @"params": @{}},
        @{@"method": @"account/read", @"id": @1, @"params": @{@"refreshToken": @NO}},
        @{@"method": @"account/rateLimits/read", @"id": @2},
        @{@"method": @"account/usage/read", @"id": @3}
    ];

    @try {
        for (NSDictionary *request in requests) {
            NSData *json = [NSJSONSerialization dataWithJSONObject:request options:0 error:nil];
            [input.fileHandleForWriting writeData:json];
            [input.fileHandleForWriting writeData:[NSData dataWithBytes:"\n" length:1]];
        }
    } @catch (NSException *exception) {
        [task terminate];
        if (error) *error = QuotaError(@"无法发送额度请求");
        return nil;
    }

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 20 * NSEC_PER_SEC),
                   dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        if (task.running) [task terminate];
    });

    NSMutableData *buffer = [NSMutableData data];
    NSMutableDictionary<NSNumber *, NSDictionary *> *responses = [NSMutableDictionary dictionary];
    while (!responses[@1] || !responses[@2] || !responses[@3]) {
        NSData *chunk = output.fileHandleForReading.availableData;
        if (chunk.length == 0) break;
        [buffer appendData:chunk];

        while (buffer.length > 0) {
            const unsigned char *bytes = buffer.bytes;
            NSUInteger newline = NSNotFound;
            for (NSUInteger index = 0; index < buffer.length; index++) {
                if (bytes[index] == '\n') { newline = index; break; }
            }
            if (newline == NSNotFound) break;
            NSData *line = [buffer subdataWithRange:NSMakeRange(0, newline)];
            [buffer replaceBytesInRange:NSMakeRange(0, newline + 1) withBytes:NULL length:0];
            if (line.length == 0) continue;
            NSDictionary *message = [NSJSONSerialization JSONObjectWithData:line options:0 error:nil];
            NSNumber *messageID = [message isKindOfClass:NSDictionary.class] ? message[@"id"] : nil;
            if ([messageID isKindOfClass:NSNumber.class]) responses[messageID] = message;
        }
    }
    if (task.running) [task terminate];

    if (!responses[@1] || !responses[@2]) {
        if (error) *error = QuotaError(@"读取额度超时");
        return nil;
    }

    NSDictionary *accountResult = [self resultFromMessage:responses[@1] name:@"账号" error:error];
    if (!accountResult) return nil;
    NSDictionary *limitsResult = [self resultFromMessage:responses[@2] name:@"额度" error:error];
    if (!limitsResult) return nil;
    NSDictionary *usageResult = [responses[@3][@"result"] isKindOfClass:NSDictionary.class]
        ? responses[@3][@"result"]
        : nil;
    NSDictionary *account = accountResult[@"account"];
    if (![account isKindOfClass:NSDictionary.class]) {
        if (error) *error = QuotaError(@"Codex 尚未登录 ChatGPT");
        return nil;
    }

    NSMutableArray<NSDictionary *> *buckets = [NSMutableArray array];
    NSDictionary *byID = limitsResult[@"rateLimitsByLimitId"];
    if ([byID isKindOfClass:NSDictionary.class]) {
        for (id value in byID.allValues) if ([value isKindOfClass:NSDictionary.class]) [buckets addObject:value];
    }
    if (buckets.count == 0 && [limitsResult[@"rateLimits"] isKindOfClass:NSDictionary.class]) {
        [buckets addObject:limitsResult[@"rateLimits"]];
    }

    NSString *plan = account[@"planType"];
    NSString *creditsBalance = nil;
    NSMutableArray<NSDictionary *> *windows = [NSMutableArray array];
    for (NSDictionary *bucket in buckets) {
        if (!plan) plan = bucket[@"planType"];
        NSDictionary *credits = bucket[@"credits"];
        if ([credits isKindOfClass:NSDictionary.class]) creditsBalance = [credits[@"balance"] description];
        for (NSString *key in @[@"primary", @"secondary"]) {
            NSDictionary *value = bucket[key];
            if (![value isKindOfClass:NSDictionary.class]) continue;
            NSNumber *used = value[@"usedPercent"];
            NSNumber *duration = value[@"windowDurationMins"];
            NSNumber *resetsAt = value[@"resetsAt"];
            if (![used isKindOfClass:NSNumber.class] || ![duration isKindOfClass:NSNumber.class] || ![resetsAt isKindOfClass:NSNumber.class]) continue;
            [windows addObject:@{
                @"used": used,
                @"duration": duration,
                @"resetsAt": resetsAt,
                @"label": [self windowLabel:duration.integerValue]
            }];
        }
    }

    NSDictionary *chosen = nil;
    for (NSDictionary *window in windows) {
        if ([window[@"duration"] integerValue] == 10080) { chosen = window; break; }
        if (!chosen || [window[@"duration"] integerValue] > [chosen[@"duration"] integerValue]) chosen = window;
    }
    if (!chosen) {
        if (error) *error = QuotaError(@"没有可显示的额度窗口");
        return nil;
    }

    double used = MAX(0, MIN(100, [chosen[@"used"] doubleValue]));
    NSDictionary *resetInfo = limitsResult[@"rateLimitResetCredits"];
    NSNumber *resetCredits = [resetInfo isKindOfClass:NSDictionary.class] ? resetInfo[@"availableCount"] : nil;
    NSMutableDictionary *snapshot = [@{
        @"account": [self maskedEmail:account[@"email"]],
        @"plan": plan ?: @"未知套餐",
        @"label": chosen[@"label"],
        @"used": @(used),
        @"remaining": @(100 - used),
        @"resetsAt": chosen[@"resetsAt"],
        @"fetchedAt": [NSDate date]
    } mutableCopy];
    if ([resetCredits isKindOfClass:NSNumber.class]) snapshot[@"resetCredits"] = resetCredits;
    if (creditsBalance) snapshot[@"creditsBalance"] = creditsBalance;
    if ([chosen[@"duration"] integerValue] == 10080 && _tracker) {
        NSDictionary *todayQuota = [_tracker recordWeeklyUsedPercent:used atDate:NSDate.date];
        snapshot[@"todayWeeklyQuotaUsed"] = todayQuota[@"usedPercent"];
        snapshot[@"todayQuotaTrackingStartedAt"] = todayQuota[@"trackingStartedAt"];
    }
    [snapshot addEntriesFromDictionary:[self usageStats:usageResult ?: @{}]];
    return snapshot;
}
@end

@interface CodexQuotaObserver : NSObject
@property(nonatomic, copy) void (^onUpdate)(NSDictionary *update);
- (instancetype)initWithTracker:(QuotaDailyUsageTracker *)tracker;
- (void)start;
- (void)stop;
@end

@implementation CodexQuotaObserver {
    QuotaDailyUsageTracker *_tracker;
    NSTask *_task;
    NSString *_weeklyKind;
    NSString *_weeklyLimitId;
    BOOL _shouldRun;
}

- (instancetype)initWithTracker:(QuotaDailyUsageTracker *)tracker {
    self = [super init];
    if (self) _tracker = tracker;
    return self;
}

- (NSString *)codexPath {
    NSFileManager *manager = NSFileManager.defaultManager;
    for (NSString *path in @[@"/usr/local/bin/codex", @"/opt/homebrew/bin/codex"]) {
        if ([manager isExecutableFileAtPath:path]) return path;
    }
    NSString *pathValue = NSProcessInfo.processInfo.environment[@"PATH"];
    for (NSString *directory in [pathValue componentsSeparatedByString:@":"]) {
        NSString *candidate = [directory stringByAppendingPathComponent:@"codex"];
        if ([manager isExecutableFileAtPath:candidate]) return candidate;
    }
    return nil;
}

- (void)send:(NSDictionary *)payload toHandle:(NSFileHandle *)handle {
    NSData *json = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    if (!json) return;
    @try {
        [handle writeData:json];
        [handle writeData:[NSData dataWithBytes:"\n" length:1]];
    } @catch (__unused NSException *exception) {
    }
}

- (void)recordWindow:(NSDictionary *)window {
    NSNumber *used = window[@"usedPercent"];
    if (![used isKindOfClass:NSNumber.class]) return;
    NSDictionary *tracking = [_tracker recordWeeklyUsedPercent:used.doubleValue atDate:NSDate.date];
    NSMutableDictionary *update = [@{
        @"currentUsed": @(MAX(0, MIN(100, used.doubleValue))),
        @"todayWeeklyQuotaUsed": tracking[@"usedPercent"],
        @"todayQuotaTrackingStartedAt": tracking[@"trackingStartedAt"]
    } mutableCopy];
    if ([window[@"resetsAt"] isKindOfClass:NSNumber.class]) update[@"resetsAt"] = window[@"resetsAt"];
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.onUpdate) self.onUpdate(update);
    });
}

- (void)handleMessage:(NSDictionary *)message {
    NSDictionary *limits = nil;
    if ([message[@"id"] integerValue] == 101 && [message[@"result"] isKindOfClass:NSDictionary.class]) {
        limits = message[@"result"];
    } else if ([message[@"method"] isEqual:@"account/rateLimits/updated"]) {
        NSDictionary *params = message[@"params"];
        limits = [params isKindOfClass:NSDictionary.class] ? params[@"rateLimits"] : nil;
    }
    if (![limits isKindOfClass:NSDictionary.class]) return;

    NSDictionary *weekly = QuotaWeeklyWindowFromLimits(limits);
    if (weekly) {
        _weeklyKind = weekly[@"kind"];
        _weeklyLimitId = weekly[@"limitId"];
        [self recordWindow:weekly];
        return;
    }

    if (_weeklyKind.length == 0) return;
    NSString *limitId = [limits[@"limitId"] isKindOfClass:NSString.class] ? limits[@"limitId"] : nil;
    if (_weeklyLimitId.length > 0 && limitId.length > 0 && ![_weeklyLimitId isEqual:limitId]) return;
    NSDictionary *sparseWindow = limits[_weeklyKind];
    if ([sparseWindow isKindOfClass:NSDictionary.class]) [self recordWindow:sparseWindow];
}

- (void)start {
    if (_task.running) return;
    NSString *codex = [self codexPath];
    if (!codex) return;
    _shouldRun = YES;
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:codex];
    task.arguments = @[@"app-server"];
    NSPipe *input = [NSPipe pipe];
    NSPipe *output = [NSPipe pipe];
    task.standardInput = input;
    task.standardOutput = output;
    task.standardError = [NSFileHandle fileHandleWithNullDevice];
    if (![task launchAndReturnError:nil]) return;
    _task = task;
    [self send:@{@"method": @"initialize", @"id": @100,
                 @"params": @{@"clientInfo": @{@"name": @"codex_quota_observer",
                                                   @"title": @"Codex Quota Observer",
                                                   @"version": @"0.6.1"}}}
          toHandle:input.fileHandleForWriting];
    [self send:@{@"method": @"initialized", @"params": @{}} toHandle:input.fileHandleForWriting];
    [self send:@{@"method": @"account/rateLimits/read", @"id": @101} toHandle:input.fileHandleForWriting];

    __weak typeof(self) weakSelf = self;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        NSMutableData *buffer = [NSMutableData data];
        while (task.running) {
            NSData *chunk = output.fileHandleForReading.availableData;
            if (chunk.length == 0) break;
            [buffer appendData:chunk];
            while (buffer.length > 0) {
                const unsigned char *bytes = buffer.bytes;
                NSUInteger newline = NSNotFound;
                for (NSUInteger index = 0; index < buffer.length; index++) {
                    if (bytes[index] == '\n') { newline = index; break; }
                }
                if (newline == NSNotFound) break;
                NSData *line = [buffer subdataWithRange:NSMakeRange(0, newline)];
                [buffer replaceBytesInRange:NSMakeRange(0, newline + 1) withBytes:NULL length:0];
                NSDictionary *message = line.length > 0
                    ? [NSJSONSerialization JSONObjectWithData:line options:0 error:nil]
                    : nil;
                if ([message isKindOfClass:NSDictionary.class]) [weakSelf handleMessage:message];
            }
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            typeof(self) strongSelf = weakSelf;
            if (!strongSelf || strongSelf->_task != task) return;
            strongSelf->_task = nil;
            if (strongSelf->_shouldRun) {
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 30 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                    if (strongSelf->_shouldRun) [strongSelf start];
                });
            }
        });
    });
}

- (void)stop {
    _shouldRun = NO;
    if (_task.running) [_task terminate];
    _task = nil;
}
@end

@interface QuotaProgressView : NSView
@property(nonatomic) double value;
@end

@implementation QuotaProgressView
- (void)setValue:(double)value {
    _value = MAX(0, MIN(100, value));
    self.needsDisplay = YES;
}
- (void)drawRect:(NSRect)dirtyRect {
    NSRect rect = NSInsetRect(self.bounds, 0, 1);
    [[NSColor colorWithCalibratedWhite:0.88 alpha:1] setFill];
    [[NSBezierPath bezierPathWithRoundedRect:rect xRadius:5 yRadius:5] fill];
    CGFloat width = NSWidth(rect) * self.value / 100.0;
    if (width <= 0) return;
    [(self.value <= 10 ? QuotaRed() : QuotaGreen()) setFill];
    NSRect fill = NSMakeRect(NSMinX(rect), NSMinY(rect), width, NSHeight(rect));
    [[NSBezierPath bezierPathWithRoundedRect:fill xRadius:5 yRadius:5] fill];
}
@end

@interface QuotaViewController : NSViewController
@property(nonatomic, copy) dispatch_block_t onRefresh;
@property(nonatomic, copy) dispatch_block_t onQuit;
- (void)setLoading;
- (void)showSnapshot:(NSDictionary *)snapshot;
- (void)updateQuotaObservation:(NSDictionary *)update;
- (void)showError:(NSError *)error;
@end

@implementation QuotaViewController {
    NSTextField *_accountLabel;
    NSTextField *_stateLabel;
    NSTextField *_todayTokensLabel;
    NSTextField *_comparisonTokensLabel;
    NSButton *_cacheInfoButton;
    NSTextField *_cacheTimeLabel;
    NSTextField *_weekTokensLabel;
    NSTextField *_monthTokensLabel;
    NSTextField *_windowLabel;
    NSTextField *_percentLabel;
    QuotaProgressView *_progress;
    NSTextField *_usedLabel;
    NSTextField *_todayQuotaLabel;
    NSTextField *_countdownLabel;
    NSTextField *_resetLabel;
    NSTextField *_creditsLabel;
    NSTextField *_updatedLabel;
    NSDictionary *_snapshot;
    NSString *_cacheTimestamp;
}

- (NSTextField *)label:(NSString *)text size:(CGFloat)size weight:(NSFontWeight)weight color:(NSColor *)color {
    NSTextField *label = [NSTextField labelWithString:text];
    label.font = [NSFont systemFontOfSize:size weight:weight];
    label.textColor = color;
    label.backgroundColor = NSColor.clearColor;
    return label;
}

- (void)loadView {
    self.view = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 360, 360)];
    self.view.wantsLayer = YES;
    self.view.layer.backgroundColor = [NSColor colorWithCalibratedRed:0.965 green:0.975 blue:0.988 alpha:1].CGColor;

    NSTextField *title = [self label:@"Codex 实际额度" size:16 weight:NSFontWeightSemibold color:QuotaText()];
    title.frame = NSMakeRect(20, 320, 210, 24);
    [self.view addSubview:title];

    NSButton *refresh = [NSButton buttonWithTitle:@"刷新" target:self action:@selector(refreshClicked:)];
    refresh.bezelStyle = NSBezelStyleInline;
    refresh.frame = NSMakeRect(266, 318, 46, 26);
    [self.view addSubview:refresh];

    NSButton *quit = [NSButton buttonWithTitle:@"退出" target:self action:@selector(quitClicked:)];
    quit.bezelStyle = NSBezelStyleInline;
    quit.frame = NSMakeRect(310, 318, 42, 26);
    [self.view addSubview:quit];

    _accountLabel = [self label:@"正在读取账号…" size:11 weight:NSFontWeightRegular color:QuotaMuted()];
    _accountLabel.frame = NSMakeRect(20, 293, 240, 18);
    [self.view addSubview:_accountLabel];

    _stateLabel = [self label:@"连接中" size:10 weight:NSFontWeightSemibold color:QuotaGreen()];
    _stateLabel.alignment = NSTextAlignmentRight;
    _stateLabel.frame = NSMakeRect(270, 293, 70, 18);
    [self.view addSubview:_stateLabel];

    _todayTokensLabel = [self label:@"今日（本机实时）：正在读取…" size:11 weight:NSFontWeightSemibold color:QuotaText()];
    _todayTokensLabel.frame = NSMakeRect(20, 267, 320, 18);
    [self.view addSubview:_todayTokensLabel];

    _comparisonTokensLabel = [self label:@"昨日（官方）：正在读取…" size:11 weight:NSFontWeightRegular color:QuotaText()];
    _comparisonTokensLabel.frame = NSMakeRect(20, 246, 320, 18);
    [self.view addSubview:_comparisonTokensLabel];

    _cacheInfoButton = [NSButton buttonWithTitle:@"ⓘ" target:self action:@selector(cacheInfoClicked:)];
    _cacheInfoButton.bezelStyle = NSBezelStyleInline;
    _cacheInfoButton.font = [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold];
    _cacheInfoButton.contentTintColor = QuotaYellow();
    _cacheInfoButton.frame = NSMakeRect(136, 243, 26, 24);
    _cacheInfoButton.toolTip = @"查看缓存数据说明";
    _cacheInfoButton.hidden = YES;
    [self.view addSubview:_cacheInfoButton];

    _cacheTimeLabel = [self label:@"" size:9 weight:NSFontWeightRegular color:QuotaYellow()];
    _cacheTimeLabel.frame = NSMakeRect(160, 246, 180, 18);
    _cacheTimeLabel.hidden = YES;
    [self.view addSubview:_cacheTimeLabel];

    _weekTokensLabel = [self label:@"本周：正在读取…" size:11 weight:NSFontWeightRegular color:QuotaText()];
    _weekTokensLabel.frame = NSMakeRect(20, 225, 320, 18);
    [self.view addSubview:_weekTokensLabel];

    _monthTokensLabel = [self label:@"本月：正在读取…" size:11 weight:NSFontWeightRegular color:QuotaText()];
    _monthTokensLabel.frame = NSMakeRect(20, 204, 320, 18);
    [self.view addSubview:_monthTokensLabel];

    _windowLabel = [self label:@"周额度" size:14 weight:NSFontWeightSemibold color:QuotaText()];
    _windowLabel.frame = NSMakeRect(20, 171, 150, 24);
    [self.view addSubview:_windowLabel];

    _percentLabel = [self label:@"--%" size:30 weight:NSFontWeightBold color:QuotaGreen()];
    _percentLabel.alignment = NSTextAlignmentRight;
    _percentLabel.frame = NSMakeRect(210, 163, 130, 38);
    [self.view addSubview:_percentLabel];

    _progress = [[QuotaProgressView alloc] initWithFrame:NSMakeRect(20, 146, 320, 12)];
    [self.view addSubview:_progress];

    _usedLabel = [self label:@"已用 --%" size:11 weight:NSFontWeightRegular color:QuotaMuted()];
    _usedLabel.frame = NSMakeRect(20, 121, 120, 18);
    [self.view addSubview:_usedLabel];

    _countdownLabel = [self label:@"刷新倒计时 --" size:11 weight:NSFontWeightSemibold color:QuotaText()];
    _countdownLabel.alignment = NSTextAlignmentRight;
    _countdownLabel.frame = NSMakeRect(140, 121, 200, 18);
    [self.view addSubview:_countdownLabel];

    _todayQuotaLabel = [self label:@"今日周额度消耗：正在累计…" size:11 weight:NSFontWeightSemibold color:QuotaText()];
    _todayQuotaLabel.frame = NSMakeRect(20, 100, 320, 18);
    _todayQuotaLabel.toolTip = @"累计官方周额度已用百分比的上涨量；滚动释放造成的下降不会扣减。";
    [self.view addSubview:_todayQuotaLabel];

    NSBox *divider = [[NSBox alloc] initWithFrame:NSMakeRect(20, 87, 320, 1)];
    divider.boxType = NSBoxSeparator;
    [self.view addSubview:divider];

    _resetLabel = [self label:@"刷新时间：--" size:11 weight:NSFontWeightRegular color:QuotaText()];
    _resetLabel.frame = NSMakeRect(20, 61, 320, 18);
    [self.view addSubview:_resetLabel];

    _creditsLabel = [self label:@"额度重置券：--" size:11 weight:NSFontWeightRegular color:QuotaMuted()];
    _creditsLabel.frame = NSMakeRect(20, 38, 320, 18);
    [self.view addSubview:_creditsLabel];

    _updatedLabel = [self label:@"" size:10 weight:NSFontWeightRegular color:NSColor.secondaryLabelColor];
    _updatedLabel.alignment = NSTextAlignmentRight;
    _updatedLabel.frame = NSMakeRect(20, 13, 320, 16);
    [self.view addSubview:_updatedLabel];

    [NSTimer scheduledTimerWithTimeInterval:30 target:self selector:@selector(updateCountdown:) userInfo:nil repeats:YES];
}

- (NSString *)formatNumber:(double)value {
    return round(value) == value ? [NSString stringWithFormat:@"%.0f", value] : [NSString stringWithFormat:@"%.1f", value];
}

- (NSString *)formatTokensWan:(NSNumber *)tokens {
    if (![tokens isKindOfClass:NSNumber.class]) return @"暂无数据";
    NSDecimalNumber *tokenCount = [NSDecimalNumber decimalNumberWithDecimal:tokens.decimalValue];
    NSDecimalNumber *wan = [tokenCount decimalNumberByDividingBy:[NSDecimalNumber decimalNumberWithString:@"10000"]];
    NSDecimalNumberHandler *rounding = [NSDecimalNumberHandler decimalNumberHandlerWithRoundingMode:NSRoundPlain
                                                                                              scale:1
                                                                                   raiseOnExactness:NO
                                                                                    raiseOnOverflow:NO
                                                                                   raiseOnUnderflow:NO
                                                                                raiseOnDivideByZero:NO];
    wan = [wan decimalNumberByRoundingAccordingToBehavior:rounding];
    NSNumberFormatter *formatter = [[NSNumberFormatter alloc] init];
    formatter.numberStyle = NSNumberFormatterDecimalStyle;
    formatter.minimumFractionDigits = 1;
    formatter.maximumFractionDigits = 1;
    formatter.roundingMode = NSNumberFormatterRoundHalfUp;
    formatter.usesGroupingSeparator = NO;
    if (tokens.longLongValue >= 100000000) {
        NSInteger yi = wan.integerValue / 10000;
        NSDecimalNumber *remainder = [wan decimalNumberBySubtracting:
            [NSDecimalNumber decimalNumberWithMantissa:(unsigned long long)yi exponent:4 isNegative:NO]];
        if ([remainder compare:NSDecimalNumber.zero] == NSOrderedSame) {
            return [NSString stringWithFormat:@"%ld亿", (long)yi];
        }
        return [NSString stringWithFormat:@"%ld亿%@万", (long)yi, [formatter stringFromNumber:remainder]];
    }
    return [NSString stringWithFormat:@"%@万", [formatter stringFromNumber:wan]];
}

- (NSAttributedString *)aggregateTextWithPrefix:(NSString *)prefix
                                 officialTokens:(NSNumber *)officialTokens
                                     todayTokens:(NSNumber *)todayTokens
                                          cached:(BOOL)cached {
    NSDictionary *normal = @{
        NSFontAttributeName: [NSFont systemFontOfSize:11 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: QuotaText()
    };
    NSDictionary *officialStyle = @{
        NSFontAttributeName: [NSFont systemFontOfSize:11 weight:NSFontWeightRegular],
        NSForegroundColorAttributeName: cached ? QuotaYellow() : QuotaText()
    };
    NSMutableAttributedString *text = [[NSMutableAttributedString alloc] initWithString:prefix attributes:normal];
    NSString *official = [NSString stringWithFormat:@"%@（官方历史）", [self formatTokensWan:officialTokens]];
    [text appendAttributedString:[[NSAttributedString alloc] initWithString:official attributes:officialStyle]];
    NSString *today = [NSString stringWithFormat:@" + %@（今日实时）", [self formatTokensWan:todayTokens]];
    [text appendAttributedString:[[NSAttributedString alloc] initWithString:today attributes:normal]];
    return text;
}

- (void)setLoading {
    _stateLabel.stringValue = @"刷新中";
    _stateLabel.textColor = NSColor.systemOrangeColor;
}

- (void)showSnapshot:(NSDictionary *)snapshot {
    _snapshot = snapshot;
    _accountLabel.stringValue = [NSString stringWithFormat:@"%@ · %@", snapshot[@"account"], snapshot[@"plan"]];
    _stateLabel.stringValue = @"实时";
    _stateLabel.textColor = QuotaGreen();
    _todayTokensLabel.stringValue = [NSString stringWithFormat:@"今日（本机实时）：%@", [self formatTokensWan:snapshot[@"todayTokens"]]];
    BOOL officialIsCached = [snapshot[@"officialIsCached"] boolValue];
    _comparisonTokensLabel.textColor = officialIsCached ? QuotaYellow() : QuotaText();
    _comparisonTokensLabel.frame = officialIsCached ? NSMakeRect(20, 246, 116, 18) : NSMakeRect(20, 246, 320, 18);
    _comparisonTokensLabel.stringValue = officialIsCached
        ? [NSString stringWithFormat:@"%@：%@", snapshot[@"comparisonLabel"] ?: @"昨日", [self formatTokensWan:snapshot[@"comparisonTokens"]]]
        : [NSString stringWithFormat:@"%@（官方 · %@）：%@",
             snapshot[@"comparisonLabel"] ?: @"昨日",
             snapshot[@"comparisonDate"] ?: @"--",
             [self formatTokensWan:snapshot[@"comparisonTokens"]]];

    _cacheInfoButton.hidden = !officialIsCached;
    _cacheTimeLabel.hidden = !officialIsCached;
    _cacheTimestamp = nil;
    if (officialIsCached && [snapshot[@"officialCacheFetchedAt"] isKindOfClass:NSNumber.class]) {
        NSDateFormatter *cacheFormatter = [[NSDateFormatter alloc] init];
        cacheFormatter.locale = [NSLocale localeWithLocaleIdentifier:@"zh_CN"];
        cacheFormatter.dateFormat = @"MM-dd HH:mm:ss";
        NSDate *cacheDate = [NSDate dateWithTimeIntervalSince1970:[snapshot[@"officialCacheFetchedAt"] doubleValue]];
        _cacheTimestamp = [cacheFormatter stringFromDate:cacheDate];
        _cacheTimeLabel.stringValue = [NSString stringWithFormat:@"（数据缓存时间%@）", _cacheTimestamp];
    } else {
        _cacheTimeLabel.stringValue = @"";
    }

    _weekTokensLabel.attributedStringValue = [self aggregateTextWithPrefix:@"本周："
                                                            officialTokens:snapshot[@"weekOfficialTokens"]
                                                                todayTokens:snapshot[@"todayTokens"]
                                                                     cached:officialIsCached];
    _monthTokensLabel.attributedStringValue = [self aggregateTextWithPrefix:@"本月："
                                                             officialTokens:snapshot[@"monthOfficialTokens"]
                                                                 todayTokens:snapshot[@"todayTokens"]
                                                                      cached:officialIsCached];
    _windowLabel.stringValue = snapshot[@"label"];
    double remaining = [snapshot[@"remaining"] doubleValue];
    double used = [snapshot[@"used"] doubleValue];
    _percentLabel.stringValue = [[self formatNumber:remaining] stringByAppendingString:@"%"];
    _percentLabel.textColor = remaining <= 10 ? QuotaRed() : QuotaGreen();
    _progress.value = remaining;
    _usedLabel.stringValue = [NSString stringWithFormat:@"已用 %@%%", [self formatNumber:used]];
    NSNumber *todayQuotaUsed = snapshot[@"todayWeeklyQuotaUsed"];
    _todayQuotaLabel.stringValue = [todayQuotaUsed isKindOfClass:NSNumber.class]
        ? [NSString stringWithFormat:@"今日周额度消耗：约 %@%%", [self formatNumber:todayQuotaUsed.doubleValue]]
        : @"今日周额度消耗：暂无数据";

    NSDateFormatter *dateFormatter = [[NSDateFormatter alloc] init];
    dateFormatter.locale = [NSLocale localeWithLocaleIdentifier:@"zh_CN"];
    dateFormatter.dateFormat = @"yyyy-MM-dd HH:mm";
    NSDate *reset = [NSDate dateWithTimeIntervalSince1970:[snapshot[@"resetsAt"] doubleValue]];
    _resetLabel.stringValue = [NSString stringWithFormat:@"刷新时间：%@", [dateFormatter stringFromDate:reset]];

    NSString *resetCredits = snapshot[@"resetCredits"] ? [NSString stringWithFormat:@"%@ 次", snapshot[@"resetCredits"]] : @"未知";
    NSString *balance = snapshot[@"creditsBalance"] ? [NSString stringWithFormat:@" · credits %@", snapshot[@"creditsBalance"]] : @"";
    _creditsLabel.stringValue = [NSString stringWithFormat:@"额度重置券：%@（不会自动使用）%@", resetCredits, balance];

    NSDateFormatter *timeFormatter = [[NSDateFormatter alloc] init];
    timeFormatter.dateFormat = @"HH:mm:ss";
    _updatedLabel.stringValue = [NSString stringWithFormat:@"更新于 %@", [timeFormatter stringFromDate:snapshot[@"fetchedAt"]]];
    [self updateCountdown:nil];
}

- (void)updateQuotaObservation:(NSDictionary *)update {
    NSNumber *todayQuotaUsed = update[@"todayWeeklyQuotaUsed"];
    if ([todayQuotaUsed isKindOfClass:NSNumber.class]) {
        _todayQuotaLabel.stringValue = [NSString stringWithFormat:@"今日周额度消耗：约 %@%%",
                                         [self formatNumber:todayQuotaUsed.doubleValue]];
    }
    if (!_snapshot) return;
    NSMutableDictionary *merged = [_snapshot mutableCopy];
    [merged addEntriesFromDictionary:update];
    NSNumber *currentUsed = update[@"currentUsed"];
    if ([currentUsed isKindOfClass:NSNumber.class]) {
        merged[@"used"] = currentUsed;
        merged[@"remaining"] = @(100 - MAX(0, MIN(100, currentUsed.doubleValue)));
    }
    merged[@"fetchedAt"] = NSDate.date;
    [self showSnapshot:merged];
}

- (void)showError:(NSError *)error {
    _stateLabel.stringValue = @"读取失败";
    _stateLabel.textColor = QuotaRed();
    _accountLabel.stringValue = error.localizedDescription;
}

- (void)cacheInfoClicked:(id)sender {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"官方接口当前不可用";
    alert.informativeText = _cacheTimestamp.length > 0
        ? [NSString stringWithFormat:@"黄色数据来自本机缓存。\n数据缓存时间：%@", _cacheTimestamp]
        : @"黄色数据来自本机缓存。";
    [alert addButtonWithTitle:@"知道了"];
    [alert runModal];
}

- (void)updateCountdown:(NSTimer *)timer {
    if (!_snapshot) return;
    NSInteger seconds = MAX(0, [_snapshot[@"resetsAt"] doubleValue] - NSDate.date.timeIntervalSince1970);
    NSInteger days = seconds / 86400;
    NSInteger hours = (seconds % 86400) / 3600;
    NSInteger minutes = (seconds % 3600) / 60;
    NSMutableArray *parts = [NSMutableArray array];
    if (days > 0) [parts addObject:[NSString stringWithFormat:@"%ld天", (long)days]];
    if (hours > 0 || days > 0) [parts addObject:[NSString stringWithFormat:@"%ld小时", (long)hours]];
    [parts addObject:[NSString stringWithFormat:@"%ld分", (long)minutes]];
    _countdownLabel.stringValue = [@"刷新倒计时 " stringByAppendingString:[parts componentsJoinedByString:@" "]];
}

- (void)refreshClicked:(id)sender { if (self.onRefresh) self.onRefresh(); }
- (void)quitClicked:(id)sender { if (self.onQuit) self.onQuit(); }
@end

@interface AppDelegate : NSObject <NSApplicationDelegate>
@end

@implementation AppDelegate {
    NSStatusItem *_statusItem;
    NSPopover *_popover;
    QuotaViewController *_controller;
    CodexQuotaClient *_client;
    QuotaDailyUsageTracker *_tracker;
    CodexQuotaObserver *_observer;
    BOOL _loading;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    _tracker = [[QuotaDailyUsageTracker alloc] init];
    _client = [[CodexQuotaClient alloc] initWithTracker:_tracker];
    _observer = [[CodexQuotaObserver alloc] initWithTracker:_tracker];
    _controller = [[QuotaViewController alloc] init];
    _statusItem = [NSStatusBar.systemStatusBar statusItemWithLength:NSVariableStatusItemLength];
    _statusItem.button.title = @"C …";
    _statusItem.button.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightSemibold];
    _statusItem.button.target = self;
    _statusItem.button.action = @selector(togglePopover:);
    _statusItem.button.toolTip = @"Codex 实际额度";

    _popover = [[NSPopover alloc] init];
    _popover.contentSize = NSMakeSize(360, 360);
    _popover.behavior = NSPopoverBehaviorTransient;
    _popover.animates = YES;
    _popover.contentViewController = _controller;

    __weak typeof(self) weakSelf = self;
    _controller.onRefresh = ^{ [weakSelf refresh]; };
    _controller.onQuit = ^{ [NSApp terminate:nil]; };
    _observer.onUpdate = ^(NSDictionary *update) {
        typeof(self) strongSelf = weakSelf;
        if (!strongSelf) return;
        [strongSelf->_controller updateQuotaObservation:update];
        NSNumber *currentUsed = update[@"currentUsed"];
        if ([currentUsed isKindOfClass:NSNumber.class]) {
            strongSelf->_statusItem.button.title = [NSString stringWithFormat:@"C %.0f%%", 100 - currentUsed.doubleValue];
        }
    };
    [_observer start];

    [self refresh];
    [NSTimer scheduledTimerWithTimeInterval:300 target:self selector:@selector(autoRefresh:) userInfo:nil repeats:YES];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.6 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [weakSelf showPopover];
    });
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    [_observer stop];
}

- (void)autoRefresh:(NSTimer *)timer { [self refresh]; }

- (void)togglePopover:(id)sender {
    _popover.shown ? [_popover performClose:nil] : [self showPopover];
}

- (void)showPopover {
    if (!_statusItem.button) return;
    [_popover showRelativeToRect:_statusItem.button.bounds ofView:_statusItem.button preferredEdge:NSMinYEdge];
}

- (void)refresh {
    if (_loading) return;
    _loading = YES;
    [_controller setLoading];
    __weak typeof(self) weakSelf = self;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        typeof(self) backgroundSelf = weakSelf;
        if (!backgroundSelf) return;
        NSError *error = nil;
        NSDictionary *snapshot = [backgroundSelf->_client fetch:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            typeof(self) strongSelf = weakSelf;
            if (!strongSelf) return;
            strongSelf->_loading = NO;
            if (snapshot) {
                [strongSelf->_controller showSnapshot:snapshot];
                strongSelf->_statusItem.button.title = [NSString stringWithFormat:@"C %.0f%%", [snapshot[@"remaining"] doubleValue]];
            } else {
                [strongSelf->_controller showError:error ?: QuotaError(@"未知错误")];
                strongSelf->_statusItem.button.title = @"C !";
            }
        });
    });
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        AppDelegate *delegate = [[AppDelegate alloc] init];
        app.delegate = delegate;
        [app run];
    }
    return 0;
}

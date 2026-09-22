// Pink Diamond iOS shell bridge (Objective-C++).
// Thin UIKit-agnostic glue so the Swift kit and the C vortex kernel can be
// dropped into the shared iOS/macOS target listed in the language directive.
#import <Foundation/Foundation.h>

@interface PDThemeBridge : NSObject
+ (NSString *)themeForAccount:(NSString *)plan apiBalance:(double)balance;
@end

@implementation PDThemeBridge
+ (NSString *)themeForAccount:(NSString *)plan apiBalance:(double)balance {
    // Free stays on the default facet; paid tiers could pick richer glass.
    if ([plan isEqualToString:@"free"]) return @"neon-rose";
    return balance > 25.0 ? @"amethyst" : @"neon-rose";
}
@end
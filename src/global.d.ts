import { UserConfig, Config, resolveConfig } from 'emmet';
import { ElementType, AttributeToken as _AttributeToken } from '@emmetio/html-matcher';

declare global {
    type AttributeToken = _AttributeToken;
    type TextRange = [number, number];
    type CSSTokenRange = [number, number, number];

    interface SelectItemModel {
        start: number;
        end: number;
        ranges: TextRange[];
    }

    interface ContextTag {
        name: string;
        type: ElementType;
        start: number;
        end: number;
        attributes?: AttributeToken[];
    }

    interface CSSSection {
        start: number;
        end: number;
        bodyStart: number;
        bodyEnd: number;
    }

    interface EmmetUserConfig extends UserConfig {
        preview?: boolean;
        inline?: boolean;
    }

    interface EmmetConfig extends Config {
        jsx?: boolean;
    }
}

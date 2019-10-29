import { UserConfig, Config, resolveConfig } from 'emmet';

declare global {
    interface EmmetUserConfig extends UserConfig {
        preview?: boolean;
        inline?: boolean;
    }

    interface EmmetConfig extends Config {
        jsx?: boolean;
    }
}
